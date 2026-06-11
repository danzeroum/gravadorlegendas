"""Servidor HTTP FastAPI para acesso remoto aos modelos.

Fornece endpoints para tradução, resumo e geração de respostas,
permitindo que os modelos pesados rodem em um container Docker
enquanto a UI leve roda no desktop.
"""
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
    """Retorna (ou cria) o tradutor local."""
    global _translator_local
    if _translator_local is None:
        _translator_local = TranslatorMarianMT()
    return _translator_local


def _get_translator_api() -> TranslatorAPI:
    """Retorna (ou cria) o tradutor via API."""
    global _translator_api
    if _translator_api is None:
        _translator_api = TranslatorAPI()
    return _translator_api


def _get_summarizer() -> Summarizer:
    """Retorna (ou cria) o resumidor."""
    global _summarizer
    if _summarizer is None:
        _summarizer = Summarizer()
    return _summarizer


def _get_local_generator() -> LocalGenerator:
    """Retorna (ou cria) o gerador local de respostas."""
    global _local_generator
    if _local_generator is None:
        _local_generator = LocalGenerator()
    return _local_generator


def _get_api_generator() -> APIGenerator:
    """Retorna (ou cria) o gerador via API de respostas."""
    global _api_generator
    if _api_generator is None:
        _api_generator = APIGenerator()
    return _api_generator


class TranslateRequest(BaseModel):
    """Schema para requisição de tradução."""
    text: str
    src: str = "eng"
    tgt: str = "por"
    use_api: bool = False


class TranslateResponse(BaseModel):
    """Schema para resposta de tradução."""
    translated: str
    source: str = "local"


class SummarizeRequest(BaseModel):
    """Schema para requisição de resumo."""
    text: str
    model: str = "gpt-3.5-turbo"
    system_prompt: str | None = None
    user_prompt: str | None = None


class GenerateRequest(BaseModel):
    """Schema para requisição de geração de resposta."""
    question: str
    context: str
    use_api: bool = False


@app.get("/health")
def health():
    """Health check do serviço."""
    return {"status": "ok", "timestamp": time.time()}


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    """Traduz texto entre idiomas.

    Usa o modelo local MarianMT por padrão, ou API
    se use_api=True.
    """
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
    """Gera resumo do texto fornecido via LLM."""
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
    """Gera resposta Globish para uma pergunta no contexto.

    Tenta LLM local primeiro; se falhar, faz fallback para API.
    """
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
