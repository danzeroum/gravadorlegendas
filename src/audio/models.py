"""Gerenciamento de download e cache de modelos de áudio + dataclasses.

Os modelos são baixados para ~/.cache/gravador/audio/.

A partir da Frente D do plano de curto prazo, este módulo também
define o dataclass :class:`CaptionSegment` usado pelo exportador de
legendas SRT/VTT.
"""
from dataclasses import dataclass
from pathlib import Path

_MODELS_DIR = Path.home() / ".cache" / "gravador" / "audio"


def get_models_dir() -> Path:
    """Retorna o diretório de cache de modelos, criando se necessário."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return _MODELS_DIR


def download_whisper(size: str = "tiny") -> Path:
    """Garante que o modelo Whisper esteja baixado e retorna o caminho."""
    from faster_whisper import WhisperModel
    cache = get_models_dir() / "whisper"
    model = WhisperModel(size, download_root=str(cache), device="cpu")
    _ = model.model
    return cache


def download_silero_vad():
    """Garante que o modelo Silero VAD esteja carregado."""
    import silero_vad
    silero_vad.load_silero_vad()


# ---------------------------------------------------------------------------
# Frente D — dataclass de segmento de legenda
# ---------------------------------------------------------------------------


@dataclass
class CaptionSegment:
    """Segmento de legenda transcrito, com timestamps absolutos.

    Attributes:
        start: Tempo de início em segundos, absoluto desde o início
            da sessão de gravação (não relativo a uma janela de batch).
        end: Tempo de fim em segundos, absoluto.
        text: Texto transcrito, sem whitespace nas bordas. Não deve
            ser vazio — segmentos vazios (silêncio) devem ser filtrados
            antes de chegar ao exportador (cobre T6.6 do plano de
            testes — sem legenda alucinada em silêncio).
    """

    start: float
    end: float
    text: str

    def __post_init__(self):
        # Garantia defensiva: texto sempre stripped. Não rejeitamos
        # texto vazio aqui (o filtro de VAD deve fazer isso), mas
        # garantimos consistência para o exportador.
        self.text = self.text.strip() if isinstance(self.text, str) else ""

    def __iter__(self):
        # Compatibilidade com desempacotamento posicional (start, end, text).
        yield self.start
        yield self.end
        yield self.text
