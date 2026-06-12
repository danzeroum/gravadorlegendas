"""Coordenador do pipeline de áudio.

Gerencia captura, VAD, buffer, transcrição e diarização
em processos/threads separados.
"""
import threading
import multiprocessing

from src.audio.capture import AudioCapture
from src.audio.vad import VoiceActivityDetector
from src.audio.buffer import CircularAudioBuffer
from src.audio.transcribe import TranscriberProcess
from src.audio.diarize import DiarizationEngine


class AudioManager:
    """Gerencia o pipeline completo de áudio.

    Attributes:
        capture: Instância de AudioCapture.
        vad: Instância de VoiceActivityDetector.
        buffer: Instância de CircularAudioBuffer.
        diarize: Instância de DiarizationEngine.
        is_running: Indica se a captura está ativa.
        on_transcription: Callback(str) chamado ao transcrever.
        on_error: Callback(str) chamado em erro.
    """

    def __init__(self):
        self.capture = AudioCapture()
        self.vad = VoiceActivityDetector()
        self.buffer = CircularAudioBuffer()
        self.diarize = DiarizationEngine()

        self._is_running = False
        self._thread: threading.Thread | None = None
        self._transcriber: TranscriberProcess | None = None
        self._audio_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._transcript_queue: multiprocessing.Queue = multiprocessing.Queue()

        self.on_transcription = None
        self.on_error = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, device_index: int | None = None):
        """Inicia captura e transcrição."""
        if self._is_running:
            return
        self._is_running = True

        if device_index is not None:
            self.capture.device_index = device_index

        self._transcriber = TranscriberProcess(
            self._audio_queue, self._transcript_queue
        )
        self._transcriber.start()

        self.capture.start(self._audio_queue)

        self._thread = threading.Thread(target=self._pipeline_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para captura e transcrição."""
        self._is_running = False
        self.capture.stop()
        if self._transcriber:
            self._transcriber.stop()
            self._transcriber = None

    def list_devices(self) -> list[dict]:
        """Delega para AudioCapture.list_devices()."""
        return self.capture.list_devices()

    def _pipeline_loop(self):
        """Loop: coleta transcrições do processo filho."""
        while self._is_running:
            try:
                result = self._transcript_queue.get(timeout=0.5)
                if "text" in result and self.on_transcription:
                    self.on_transcription(result["text"])
                elif "error" in result and self.on_error:
                    self.on_error(result["error"])
            except Exception:
                pass
