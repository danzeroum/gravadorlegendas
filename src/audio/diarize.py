"""Diarização de falantes (offline e streaming).

Processa áudio para identificar diferentes falantes.
Offline: processa arquivo completo após gravação.
Streaming: (Sprint 3) processa em janelas deslizantes.
"""


class DiarizationEngine:
    """Motor de diarização de falantes.

    Attributes:
        enabled: Se True, a diarização está ativa.
        num_speakers: Número esperado de falantes (None = automático).
    """

    def __init__(self, enabled: bool = False, num_speakers: int | None = None):
        self.enabled = enabled
        self.num_speakers = num_speakers

    def diarize_offline(self, audio_path: str) -> list[dict]:
        """Processa arquivo WAV completo e retorna segmentos com falantes.

        Args:
            audio_path: Caminho para arquivo WAV.

        Returns:
            Lista de dicts: {start, end, speaker, text?}.
        """
        if not self.enabled:
            return []

        try:
            from diart import OnlineSpeakerDiarization
            from diart.sources import AudioFileSource
            from diart.models import EmbeddingModel

            source = AudioFileSource(audio_path)
            model = EmbeddingModel.from_pretrained(
                "pyannote/embedding", cache_dir="data/models"
            )
            pipeline = OnlineSpeakerDiarization(model)
            segmentation = pipeline(source)
            segments = []
            for turn in segmentation:
                segments.append({
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": f"Falante {turn.speaker}",
                })
            return segments
        except ImportError:
            return [{"error": "diart não instalado"}]
        except Exception as e:
            return [{"error": str(e)}]

    def diarize_streaming(self, audio_chunk: bytes) -> list[dict] | None:
        """Processa chunk de áudio em streaming (Sprint 3)."""
        raise NotImplementedError("Streaming diarization: Sprint 3")
