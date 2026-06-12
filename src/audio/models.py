"""Gerenciamento de download e cache de modelos de áudio.

Os modelos são baixados para ~/.cache/gravador/audio/.
"""
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
