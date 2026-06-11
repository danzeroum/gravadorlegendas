import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
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

    log_dir: str = os.getenv("LOG_DIR", "data/logs")
    recording_dir: str = os.getenv("RECORDING_DIR", "data/recordings")
    wordlist_path: str = os.getenv("WORDLIST_PATH", "data/wordlists/pt_50k.txt")

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_deepseek(self) -> bool:
        return bool(self.deepseek_api_key)


settings = Settings()
