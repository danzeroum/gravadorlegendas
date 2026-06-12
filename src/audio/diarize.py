"""Diarização de falantes offline e streaming.

Processa áudio para identificar diferentes falantes usando
diart (streaming) ou pyannote.audio (offline em arquivo WAV).
"""
import multiprocessing
import queue
import time
import numpy as np


class DiarizationProcess(multiprocessing.Process):
    """Processo separado para diarização de falantes.

    Args:
        input_queue: Queue que recebe chunks de áudio (bytes PCM16).
        output_queue: Queue onde segmentos com falantes são enviados.
    """

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
    ):
        super().__init__(daemon=True)
        self._input = input_queue
        self._output = output_queue
        self._stop_event = multiprocessing.Event()
        self._pipeline = None
        self._sample_rate = 16000
        self._rolling_buffer = []
        self._offset = 0.0
        self._last_speaker = None

    def stop(self):
        """Sinaliza para o processo parar."""
        self._stop_event.set()

    def _load_pipeline(self):
        """Carrega o pipeline diart (lazy, uma vez)."""
        if self._pipeline is not None:
            return True
        try:
            from diart import OnlineSpeakerDiarization
            from diart.models import EmbeddingModel
            from diart.sources import AudioFileSource
            self._AudioFileSource = AudioFileSource
            model = EmbeddingModel.from_pretrained(
                "pyannote/embedding",
                cache_dir="data/models",
            )
            self._pipeline = OnlineSpeakerDiarization(model)
            return True
        except ImportError:
            self._output.put({"error": "diart não instalado. pip install diart"})
            return False
        except Exception as e:
            self._output.put({"error": f"Erro ao carregar pipeline diart: {e}"})
            return False

    def diarize_file(self, wav_path: str) -> list[dict]:
        """Processa arquivo WAV completo e retorna segmentos com falantes.

        Args:
            wav_path: Caminho para arquivo WAV mono 16kHz.

        Returns:
            Lista de dicts: {speaker, start, end}.
        """
        if not self._load_pipeline():
            return []
        try:
            source = self._AudioFileSource(wav_path)
            segmentation = self._pipeline(source)
            segments = []
            for turn, _, speaker in segmentation.itertracks(yield_label=True):
                segments.append({
                    "speaker": str(speaker),
                    "start": round(turn.start, 2),
                    "end": round(turn.end, 2),
                })
            return segments
        except Exception as e:
            self._output.put({"error": f"diarize_file error: {e}"})
            return []

    def run(self):
        """Loop principal: processa chunks e emite segmentos."""
        if not self._load_pipeline():
            return

        chunk_duration = 0.5
        chunk_samples = int(self._sample_rate * chunk_duration)
        audio_buffer = b""
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            try:
                chunk = self._input.get(timeout=0.5)
            except queue.Empty:
                if audio_buffer and time.monotonic() - last_flush > 3.0:
                    self._flush_buffer()
                    audio_buffer = b""
                    last_flush = time.monotonic()
                continue

            audio_buffer += chunk

            if len(audio_buffer) >= chunk_samples * 2:
                self._feed_pipeline(audio_buffer)
                audio_buffer = b""
                last_flush = time.monotonic()

    def _ensure_sample_rate(self):
        pass

    def _feed_pipeline(self, audio_data: bytes):
        """Alimenta o pipeline diart com um bloco de áudio."""
        audio_array = (
            np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            / 32768.0
        )
        try:
            segmentation = self._pipeline(audio_array)
            for turn, _, speaker in segmentation.itertracks(yield_label=True):
                speaker_id = str(speaker)
                if speaker_id != self._last_speaker:
                    self._last_speaker = speaker_id
                    self._output.put({
                        "speaker": speaker_id,
                        "start": round(turn.start, 2),
                        "end": round(turn.end, 2),
                    })
        except Exception as e:
            self._output.put({"error": f"feed_pipeline error: {e}"})

    def _flush_buffer(self):
        """Força processamento do buffer restante."""
        self._last_speaker = None
