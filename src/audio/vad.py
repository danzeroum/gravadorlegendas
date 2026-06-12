"""Voice Activity Detection com Silero VAD.

Detecta quando há fala humana em um segmento de áudio.
"""
import numpy as np


class VoiceActivityDetector:
    """Detector de atividade de voz usando Silero VAD.

    Attributes:
        threshold: Limiar de probabilidade (0.0–1.0) para considerar voz.
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._model = None

    def load(self):
        """Carrega o modelo Silero VAD (lazy)."""
        if self._model is not None:
            return
        try:
            import silero_vad
            self._model = silero_vad.load_silero_vad()
        except ImportError:
            raise RuntimeError("silero-vad não instalado. pip install silero-vad")

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Retorna True se o chunk de áudio contiver fala."""
        self.load()
        import silero_vad
        audio_array = (
            np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
            / 32768.0
        )
        timestamps = silero_vad.get_speech_timestamps(
            audio_array, self._model, threshold=self.threshold
        )
        return len(timestamps) > 0
