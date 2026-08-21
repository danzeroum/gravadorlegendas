"""Coordenador do pipeline de áudio.

Gerencia captura, VAD, buffer, transcrição e diarização
em processos/threads separados.
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

        self.on_transcription = None
        self.on_segment = None
        self.on_error = None

        self._speaker_segments: deque = deque(maxlen=50)
        self._latency = LatencyTracker()
        self._overlap = OverlapCounter()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, device_index: int | str | None = None,
              enable_diarization: bool = True):
        """Inicia captura, transcrição e opcionalmente diarização.

        Args:
            device_index: Identificador do dispositivo. Em Windows, é o
                índice WASAPI (int). Em Linux, é o ID numérico ou nome
                do source PipeWire (str). None = auto-detect.
            enable_diarization: Se True, inicia diarização em tempo real.
        """
        if self._is_running:
            return
        self._is_running = True
        self._recorded_chunks.clear()
        self._speaker_segments.clear()
        self.recorded_wav = None

        if device_index is not None:
            self.capture.device_index = device_index

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

        self.capture.start(self._audio_queue)

        self._thread = threading.Thread(target=self._pipeline_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para captura, transcrição e diarização."""
        self._is_running = False
        self.capture.stop()
        if self._transcriber:
            self._transcriber.stop()
            self._transcriber = None
        if self._diarizer:
            self._diarizer.stop()
            self._diarizer = None
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
