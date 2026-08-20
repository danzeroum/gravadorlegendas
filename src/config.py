"""Configuração centralizada via variáveis de ambiente e config.json.

Carrega valores do arquivo .env (se existir) e disponibiliza
como atributos tipados da classe Settings. Valores do arquivo
config.json (gerado pela ConfigStore) sobrescrevem os do .env.

A partir da migração Linux/Fedora, esta classe também expõe as novas
opções multiplataforma: ``platform_backend``, ``audio_backend``,
``audio_source``, ``caption_source``, ``screen_capture_backend``,
``stt_model``, ``stt_device``, etc. Veja ``validate()`` para checagem.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src.config_store import config_store
from src.platform.detection import detect_os, detect_session_type

load_dotenv()


def _default_tesseract_path() -> str:
    """Retorna o caminho default do Tesseract conforme o SO."""
    if sys.platform.startswith("win"):
        return r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # Linux / macOS — assume que está no PATH
    return "tesseract"


class Settings:
    """Configurações da aplicação carregadas de variáveis de ambiente.

    Atributos:
        tesseract_path: Caminho do executável Tesseract OCR.
        openai_api_key: Chave da API OpenAI.
        deepseek_api_key: Chave da API DeepSeek.
        screen_region: Dict com top, left, width, height.
        ocr_language: Idioma padrão do OCR.
        translation_model: Nome do modelo MarianMT.
        local_llm_path: Caminho do modelo .gguf local.
        llm_threads: Número de threads para o LLM local.
        llm_ctx: Tamanho do contexto do LLM.
        log_dir: Diretório para logs.
        recording_dir: Diretório para arquivos de legenda.
        wordlist_path: Caminho da wordlist para filtro de ruído.
        platform_backend: auto | windows | linux.
        audio_backend: auto | wasapi | pipewire.
        audio_source: microphone | system | both | device.
        audio_device_id: Identificador do dispositivo selecionado.
        caption_source: auto | windows_live_captions | local_stt | screen_ocr.
        screen_capture_backend: auto | mss | portal.
        stt_model: Tamanho/nome do modelo Whisper (tiny, base, small...).
        stt_device: auto | cpu | cuda.
        sample_rate: Taxa de amostragem para captura (Hz).
        channels: Número de canais (1 = mono).
    """

    tesseract_path: str = os.getenv(
        "TESSERACT_PATH", _default_tesseract_path()
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    screen_region: dict = {
        "top": int(os.getenv("REGION_TOP", "0")),
        "left": int(os.getenv("REGION_LEFT", "50")),
        "width": int(os.getenv("REGION_WIDTH", "1820")),
        "height": int(os.getenv("REGION_HEIGHT", "80")),
    }

    ocr_language: str = os.getenv("OCR_LANGUAGE", "eng")
    translation_model: str = os.getenv(
        "TRANSLATION_MODEL",
        "Helsinki-NLP/opus-mt-tc-big-en-pt"
    )
    local_llm_path: str = os.getenv(
        "LOCAL_LLM_PATH",
        "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    )
    llm_threads: int = int(os.getenv("LLM_THREADS", "4"))
    llm_ctx: int = int(os.getenv("LLM_CTX", "2048"))

    ollama_base_url: str = os.getenv(
        "OLLAMA_BASE_URL", "https://api.buildtovalue.cloud"
    )
    ollama_username: str = os.getenv("OLLAMA_USERNAME", "")
    ollama_password: str = os.getenv("OLLAMA_PASSWORD", "")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "mistral:latest")

    log_dir: str = os.getenv("LOG_DIR", "data/logs")
    recording_dir: str = os.getenv("RECORDING_DIR", "data/recordings")
    wordlist_path: str = os.getenv("WORDLIST_PATH", "data/wordlists/pt_50k.txt")

    # --- Novas opções multiplataforma ---
    platform_backend: str = os.getenv("PLATFORM_BACKEND", "auto")
    audio_backend: str = os.getenv("AUDIO_BACKEND", "auto")
    audio_source: str = os.getenv("AUDIO_SOURCE", "system")
    audio_device_id: str = os.getenv("AUDIO_DEVICE_ID", "")
    caption_source: str = os.getenv("CAPTION_SOURCE", "auto")
    screen_capture_backend: str = os.getenv("SCREEN_CAPTURE_BACKEND", "auto")
    stt_model: str = os.getenv("STT_MODEL", "base")
    stt_device: str = os.getenv("STT_DEVICE", "auto")
    sample_rate: int = int(os.getenv("SAMPLE_RATE", "16000"))
    channels: int = int(os.getenv("CHANNELS", "1"))

    @property
    def has_ollama(self) -> bool:
        return bool(self.ollama_username and self.ollama_password)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_deepseek(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def os_type(self) -> str:
        """Sistema operacional detectado (string simples)."""
        return detect_os().value

    @property
    def session_type(self) -> str:
        """Tipo de sessão gráfica (wayland | x11 | windows | unknown)."""
        return detect_session_type().value


settings = Settings()

# Sobrescreve região de captura com valor persistido (se existir)
stored_region = config_store.get("screen_region")
if stored_region:
    settings.screen_region = stored_region


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

_VALID = {
    "platform_backend": {"auto", "windows", "linux"},
    "audio_backend": {"auto", "wasapi", "pipewire"},
    "audio_source": {"microphone", "system", "both", "device"},
    "caption_source": {"auto", "windows_live_captions", "local_stt", "screen_ocr"},
    "screen_capture_backend": {"auto", "mss", "portal"},
    "stt_device": {"auto", "cpu", "cuda"},
}


class ConfigValidationError(ValueError):
    """Erro de validação de configuração."""


def validate_settings(s=None) -> list[str]:
    """Valida as configurações críticas.

    Returns:
        Lista de mensagens de erro (vazia se tudo OK).
    """
    s = s or settings
    errors: list[str] = []

    for key, allowed in _VALID.items():
        value = getattr(s, key)
        if value not in allowed:
            errors.append(
                f"{key}={value!r} inválido. Valores aceitos: {sorted(allowed)}"
            )

    # Cross-field: audio_backend=wasapi só em Windows
    if s.audio_backend == "wasapi" and not sys.platform.startswith("win"):
        errors.append(
            "audio_backend='wasapi' só é suportado em Windows. "
            "Use 'pipewire' ou 'auto'."
        )
    if s.audio_backend == "pipewire" and sys.platform.startswith("win"):
        errors.append(
            "audio_backend='pipewire' não é suportado em Windows. "
            "Use 'wasapi' ou 'auto'."
        )

    # caption_source=windows_live_captions só em Windows
    if (
        s.caption_source == "windows_live_captions"
        and not sys.platform.startswith("win")
    ):
        errors.append(
            "caption_source='windows_live_captions' só é suportado em Windows. "
            "Use 'local_stt' ou 'auto'."
        )

    if s.sample_rate <= 0:
        errors.append(f"sample_rate deve ser positivo (atual={s.sample_rate})")
    if s.channels not in (1, 2):
        errors.append(f"channels deve ser 1 ou 2 (atual={s.channels})")

    return errors


def assert_settings_valid(s=None) -> None:
    """Lança ``ConfigValidationError`` se settings estiverem inválidas."""
    errors = validate_settings(s)
    if errors:
        raise ConfigValidationError("; ".join(errors))
