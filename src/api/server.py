import time
import logging

from fastapi import FastAPI
from pydantic import BaseModel

from src.translation.marianmt import TranslatorMarianMT
from src.translation.api import TranslatorAPI
from src.nlp.summarizer import Summarizer
from src.nlp.answer_generator import LocalGenerator, APIGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Assistente de Reunião API", version="1.0.0")

_translator_local: TranslatorMarianMT | None = None
_translator_api: TranslatorAPI | None = None
_summarizer: Summarizer | None = None
_local_generator: LocalGenerator | None = None
_api_generator: APIGenerator | None = None


def _get_translator() -> TranslatorMarianMT:
    global _translator_local
    if _translator_local is None:
        _translator_local = TranslatorMarianMT()
    return _translator_local


def _get_translator_api() -> TranslatorAPI:
    global _translator_api
    if _translator_api is None:
        _translator_api = TranslatorAPI()
    return _translator_api


def _get_summarizer() -> Summarizer:
    global _summarizer
    if _summarizer is None:
        _summarizer = Summarizer()
    return _summarizer


def _get_local_generator() -> LocalGenerator:
    global _local_generator
    if _local_generator is None:
        _local_generator = LocalGenerator()
    return _local_generator


def _get_api_generator() -> APIGenerator:
    global _api_generator
    if _api_generator is None:
        _api_generator = APIGenerator()
    return _api_generator


# --- Schemas ---
class TranslateRequest(BaseModel):
    text: str
    src: str = "eng"
    tgt: str = "por"
    use_api: bool = False


class TranslateResponse(BaseModel):
    translated: str
    source: str = "local"


class SummarizeRequest(BaseModel):
    text: str
    model: str = "gpt-3.5-turbo"
    system_prompt: str | None = None
    user_prompt: str | None = None


class GenerateRequest(BaseModel):
    question: str
    context: str
    use_api: bool = False


# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    start = time.time()
    if req.use_api:
        result = _get_translator_api().translate(req.text, req.src, req.tgt)
        source = "api"
    else:
        result = _get_translator().translate(req.text, req.src, req.tgt)
        source = "local"
    logger.info(
        "translate", extra={
            "text_len": len(req.text), "source": source,
            "duration_ms": int((time.time() - start) * 1000),
        }
    )
    return TranslateResponse(translated=result, source=source)


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    start = time.time()
    result = _get_summarizer().summarize(
        req.text, req.model, req.system_prompt, req.user_prompt
    )
    logger.info(
        "summarize", extra={
            "text_len": len(req.text),
            "duration_ms": int((time.time() - start) * 1000),
        }
    )
    return {"summary": result}


@app.post("/generate")
def generate(req: GenerateRequest):
    start = time.time()
    if req.use_api:
        result = _get_api_generator().generate(req.question, req.context)
        source = "api"
    else:
        try:
            result = _get_local_generator().generate(req.question, req.context)
            source = "local"
        except RuntimeError:
            result = _get_api_generator().generate(req.question, req.context)
            source = "api_fallback"
    logger.info(
        "generate", extra={
            "source": source,
            "duration_ms": int((time.time() - start) * 1000),
        }
    )
    return {"answer": result, "source": source}
