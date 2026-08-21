"""Coordenador do pipeline de áudio.

Gerencia captura, VAD, buffer, transcrição e diarização
em processos/threads separados.

A partir do plano de curto prazo, este módulo também integra:

- **Frente A** — gravação dual-track (mic + sistema em arquivos WAV
  separados), ativada via ``record_raw=True`` no ``start()`` ou via
  ``settings.record_raw_audio``.
- **Frente B** — mixagem real ``audio_source=both``: quando ativa,
  abre duas capturas paralelas (mic + monitor do sistema) e combina
  os frames via :class:`AudioMixer` antes de alimentar o buffer.
- **Frente C** — RNNoise (supressão de ruído em tempo real), ativada
  via ``noise_suppression=True`` ou ``settings.noise_suppression``.
  Inserido entre a captura/mixagem e o buffer circular.
"""
import os
import threading
import multiprocessing
import wave
import tempfile
from collections import deque

import structlog

from src.audio.capture import AudioCapture
from src.audio.vad import VoiceActivityDetector
from src.audio.buffer import CircularAudioBuffer
from src.audio.transcribe import TranscriberProcess
from src.audio.diarize import DiarizationProcess
from src.audio.metrics import LatencyTracker, OverlapCounter
from src.audio.recorder import DualTrackRecorder, DualTrackResult
from src.audio.mixer import AudioMixer
from src.config import settings

_logger = structlog.get_logger()


_SPEAKER_MERGE_TOLERANCE = 0.3


class AudioManager:
    """Gerencia o pipeline completo de áudio.

    Attributes:
        capture: Instância de AudioCapture.
        vad: Instância de VoiceActivityDetector.
        buffer: Instância de CircularAudioBuffer.
        is_running: Indica se a captura está ativa.
        on_transcription: Callback(text, speaker) chamado ao transcrever.
        on_error: Callback(str) chamado em erro.
        recorded_wav: Caminho do WAV salvo ao parar (None se vazio).
    """

    def __init__(self):
        self.capture = AudioCapture()
        self.vad = VoiceActivityDetector()
        self.buffer = CircularAudioBuffer()

        self._is_running = False
        self._thread: threading.Thread | None = None
        self._transcriber: TranscriberProcess | None = None
        self._diarizer: DiarizationProcess | None = None
        self._audio_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._transcript_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._diarization_queue: multiprocessing.Queue = multiprocessing.Queue()

        self._recorded_chunks: list[bytes] = []
        self.recorded_wav: str | None = None

        # Frente A: dual-track recorder (None se record_raw=False).
        self._dual_recorder: DualTrackRecorder | None = None
        self._dual_recorder_result: DualTrackResult | None = None

        # Frente B: mixer e segunda captura (system) para audio_source=both.
        self._mixer: AudioMixer | None = None
        self._system_capture: AudioCapture | None = None
        self._system_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._fanout_thread: threading.Thread | None = None
        # Fila "master" que recebe chunks do(s) stream(s) de captura e
        # alimenta o fan-out (recorder + queue do Whisper).
        self._master_queue: multiprocessing.Queue = multiprocessing.Queue()

        # Frente C: filtro de ruído (None se noise_suppression=False).
        self._noise_filter = None

        self.on_transcription = None
        self.on_segment = None
        self.on_error = None

        self._speaker_segments: deque = deque(maxlen=50)
        self._latency = LatencyTracker()
        self._overlap = OverlapCounter()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def dual_recorder_result(self) -> DualTrackResult | None:
        """Resultado da última gravação dual-track (None se não gravou)."""
        return self._dual_recorder_result

    def start(self, device_index: int | str | None = None,
              enable_diarization: bool = True,
              record_raw: bool | None = None,
              noise_suppression: bool | None = None,
              system_device_index: int | str | None = None):
        """Inicia captura, transcrição e opcionalmente diarização.

        Args:
            device_index: Identificador do dispositivo. Em Windows, é o
                índice WASAPI (int). Em Linux, é o ID numérico ou nome
                do source PipeWire (str). None = auto-detect.
            enable_diarization: Se True, inicia diarização em tempo real.
            record_raw: Se True, ativa gravação dual-track (mic+sistema
                em WAVs separados). Default: ``settings.record_raw_audio``.
            noise_suppression: Se True, ativa RNNoise no pipeline.
                Default: ``settings.noise_suppression``.
            system_device_index: Para ``audio_source=both``, segundo
                dispositivo (monitor do sistema). Se None e
                ``settings.audio_source == "both"``, usa auto-detect.
        """
        if self._is_running:
            return
        self._is_running = True
        self._recorded_chunks.clear()
        self._speaker_segments.clear()
        self.recorded_wav = None
        self._dual_recorder_result = None

        # Resolve defaults das novas flags via settings.
        if record_raw is None:
            record_raw = settings.record_raw_audio
        if noise_suppression is None:
            noise_suppression = settings.noise_suppression

        if device_index is not None:
            self.capture.device_index = device_index

        # --- Frente C: inicializa filtro de ruído (lazy, antes do transcriber) ---
        if noise_suppression:
            try:
                from src.filter.noise_suppression import RNNoiseFilter
                self._noise_filter = RNNoiseFilter(
                    sample_rate=settings.sample_rate,
                )
                _logger.info(
                    "audio_manager_noise_filter_active",
                    backend=self._noise_filter.backend_name,
                )
            except Exception as e:
                _logger.error("audio_manager_noise_filter_init_failed",
                              error=str(e))
                self._noise_filter = None

        self._transcriber = TranscriberProcess(
            self._audio_queue,
            self._transcript_queue,
            model_size=settings.stt_model,
            chunk_duration=settings.stt_chunk_duration,
            language=settings.stt_language,
            task=settings.stt_task,
            beam_size=settings.stt_beam_size,
            temperature=settings.stt_temperature,
            vad_filter=settings.stt_vad_filter,
        )
        self._transcriber.start()

        if enable_diarization:
            self._diarizer = DiarizationProcess(
                self._audio_queue, self._diarization_queue
            )
            self._diarizer.start()

        # --- Frente A: dual-track recorder ---
        if record_raw:
            self._dual_recorder = DualTrackRecorder(
                output_dir=settings.recording_dir,
                sample_rate=settings.sample_rate,
                channels=settings.channels,
            )
            self._dual_recorder.start()

        # --- Frente B: audio_source=both — segunda captura + mixer ---
        if settings.audio_source == "both":
            self._mixer = AudioMixer(
                sample_rate=settings.sample_rate,
                channels=settings.channels,
            )
            # Segunda captura (sistema) — só se um device explícito foi
            # passado; caso contrário, cai para single-source com aviso.
            if system_device_index is not None:
                self._system_capture = AudioCapture(
                    device_index=system_device_index,
                    sample_rate=settings.sample_rate,
                    chunk_size=480,
                )
            else:
                _logger.warning(
                    "audio_source_both_without_system_device",
                    hint="Passar system_device_index ou configurar AUDIO_DEVICE_ID",
                )

        # Captura principal sempre alimenta a fila "master"; o fan-out
        # decide para onde cada chunk vai (Whisper + recorder).
        self.capture.start(self._master_queue)
        if self._system_capture is not None:
            self._system_capture.start(self._system_queue)

        self._thread = threading.Thread(target=self._pipeline_loop, daemon=True)
        self._thread.start()
        # Fan-out thread: lê master_queue e system_queue, aplica mixer
        # opcional, aplica RNNoise opcional, alimenta recorder + audio_queue.
        self._fanout_thread = threading.Thread(
            target=self._fanout_loop, daemon=True,
        )
        self._fanout_thread.start()

    def stop(self):
        """Para captura, transcrição e diarização.

        Garante que o ``DualTrackRecorder.stop()`` é chamado **antes**
        de finalizar os processos de captura, para não truncar o final
        do áudio (cobre T3.3 do plano de testes).
        """
        self._is_running = False
        # Frente A: fechar recorder primeiro (flush dos WAVs).
        if self._dual_recorder is not None:
            try:
                self._dual_recorder_result = self._dual_recorder.stop(timeout_s=2.0)
            except Exception as e:
                _logger.error("dual_recorder_stop_error", error=str(e))
            self._dual_recorder = None
        self.capture.stop()
        if self._system_capture is not None:
            self._system_capture.stop()
            self._system_capture = None
        if self._transcriber:
            self._transcriber.stop()
            self._transcriber = None
        if self._diarizer:
            self._diarizer.stop()
            self._diarizer = None
        if self._fanout_thread is not None:
            self._fanout_thread.join(timeout=2.0)
            self._fanout_thread = None
        self._save_recorded_wav()
        self._latency.log("audio_stop")
        self._overlap.log("audio_stop")

    def list_devices(self) -> list[dict]:
        """Delega para AudioCapture.list_devices()."""
        return self.capture.list_devices()

    def reprocess_with_diarization(self) -> list[dict]:
        """Re-processa o WAV salvo com diarização offline.

        Returns:
            Lista de segmentos: {speaker, start, end}.
        """
        if not self.recorded_wav or not os.path.isfile(self.recorded_wav):
            return []
        dp = DiarizationProcess(
            multiprocessing.Queue(), multiprocessing.Queue()
        )
        return dp.diarize_file(self.recorded_wav)

    def _save_recorded_wav(self):
        """Salva áudio capturado em arquivo WAV temporário."""
        if not self._recorded_chunks:
            self.recorded_wav = None
            return
        try:
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="gravador_")
            os.close(fd)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                for chunk in self._recorded_chunks:
                    wf.writeframes(chunk)
            self.recorded_wav = path
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))

    def _pipeline_loop(self):
        """Loop: coleta diarização + transcrição e faz merge."""
        while self._is_running:
            try:
                self._collect_diarization_nowait()
            except Exception as e:
                _logger.error("pipeline_diarization_error", error=str(e))
            try:
                self._collect_transcript()
            except Exception as e:
                _logger.error("pipeline_transcript_error", error=str(e))

    def _fanout_loop(self):
        """Loop de fan-out: lê master_queue (e system_queue), aplica
        mixagem opcional (Frente B) e RNNoise opcional (Frente C),
        e alimenta o recorder (Frente A) e a audio_queue do Whisper.

        Ordem do pipeline:
            captura -> mixagem opcional -> RNNoise opcional
                   -> [recorder + audio_queue (Whisper)]
        """
        import queue as _q

        while self._is_running:
            try:
                mic_chunk = self._master_queue.get(timeout=0.2)
            except _q.Empty:
                mic_chunk = None

            # Frente B: se mixer ativo, tenta parear com chunk do sistema
            processed = mic_chunk
            if self._mixer is not None and mic_chunk is not None:
                try:
                    sys_chunk = self._system_queue.get_nowait()
                except _q.Empty:
                    sys_chunk = b""
                # T4.3: se sistema está vazio, mix_frame repassa o mic
                processed = self._mixer.mix_frame(mic_chunk, sys_chunk)

            # Frente C: aplica RNNoise, se ativo
            if self._noise_filter is not None and processed is not None:
                try:
                    processed = self._noise_filter.process_frame(processed)
                except Exception as e:
                    _logger.error("noise_filter_process_error", error=str(e))

            if processed is None:
                continue

            # Mantém compatibilidade: armazena para _save_recorded_wav.
            self._recorded_chunks.append(processed)

            # Fan-out para o recorder dual-track (se ativo) — separa
            # mic e sistema novamente para gravar em trilhos distintos.
            # Quando mixer está ativo, gravamos apenas o trilho "mixado"
            # no mic_path e deixamos system_path vazio (decisão de
            # produto: o dual-track bruto só faz sentido sem mixagem).
            if self._dual_recorder is not None:
                if self._mixer is not None:
                    self._dual_recorder.feed_mic(processed)
                else:
                    self._dual_recorder.feed_mic(mic_chunk or b"")
                    # Tenta parear com chunk do sistema sem mixar
                    if self._system_capture is not None:
                        try:
                            sys_chunk = self._system_queue.get_nowait()
                            self._dual_recorder.feed_system(sys_chunk)
                        except _q.Empty:
                            pass

            # Alimenta o transcriber (Whisper).
            try:
                self._audio_queue.put(processed)
            except Exception:
                pass

    def _collect_diarization_nowait(self):
        """Lê segmentos de diarização pendentes (non-blocking)."""
        try:
            while True:
                seg = self._diarization_queue.get_nowait()
                if "speaker" in seg:
                    self._speaker_segments.append(seg)
                    self._overlap.feed_segments([seg])
                    if self.on_segment:
                        self.on_segment(seg)
                elif "error" in seg and self.on_error:
                    self.on_error(seg["error"])
        except Exception:
            pass

    def _collect_transcript(self):
        """Lê resultado da transcrição e encaminha com speaker."""
        try:
            result = self._transcript_queue.get(timeout=0.2)
        except Exception:
            return

        if "error" in result and self.on_error:
            self.on_error(result["error"])
            return
        if "text" not in result:
            return

        batch = result.get("batch", 0)
        self._latency.mark_receive(batch)

        speaker = self._match_speaker(
            result.get("start", 0), result.get("end", 0)
        )
        if self.on_transcription:
            self.on_transcription(result["text"], speaker)

    def _match_speaker(self, start: float, end: float) -> str | None:
        """Encontra qual falante estava ativo no intervalo [start, end].

        Usa tolerância de ±_SPEAKER_MERGE_TOLERANCEs para matching.
        """
        best = None
        best_overlap = -1.0
        for seg in list(self._speaker_segments):
            s = max(start, seg["start"])
            e = min(end, seg["end"])
            overlap = max(0.0, e - s)
            if overlap > best_overlap and overlap > _SPEAKER_MERGE_TOLERANCE:
                best = seg["speaker"]
                best_overlap = overlap
        return best
