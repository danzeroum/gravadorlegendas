"""Configuração centralizada via variáveis de ambiente e config.json.

Carrega valores do arquivo .env (se existir) e disponibiliza
como atributos tipados da classe Settings. Valores do arquivo
config.json (gerado pela ConfigStore) sobrescrevem os do .env.
"""
import os
from dotenv import load_dotenv
from src.config_store import config_store

load_dotenv()


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
    """
    tesseract_path: str = os.getenv(
        "TESSERACT_PATH",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
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

    @property
    def has_ollama(self) -> bool:
        """Retorna True se credenciais Ollama foram configuradas no .env."""
        return bool(self.ollama_username and self.ollama_password)

    @property
    def has_openai(self) -> bool:
        """Retorna True se a chave OpenAI foi configurada."""
        return bool(self.openai_api_key)

    @property
    def has_deepseek(self) -> bool:
        """Retorna True se a chave DeepSeek foi configurada."""
        return bool(self.deepseek_api_key)


settings = Settings()

# Sobrescreve região de captura com valor persistido (se existir)
stored_region = config_store.get("screen_region")
if stored_region:
    settings.screen_region = stored_region
