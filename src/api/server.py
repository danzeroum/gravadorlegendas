"""Servidor HTTP FastAPI para acesso remoto aos modelos.

Fornece endpoints para tradução, resumo, geração de respostas
e gerenciamento de provedores de LLM (/v1/llm/*).
"""
import time
import logging

from fastapi import FastAPI
from pydantic import BaseModel

from src.translation.marianmt import TranslatorMarianMT
from src.translation.api import TranslatorAPI
from src.llm.manager import llm_manager
from src.nlp.summarizer import Summarizer
from src.nlp.answer_generator import ManagedGenerator
from src.config_store import config_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Assistente de Reunião API", version="1.0.0")

_translator_local: TranslatorMarianMT | None = None
_translator_api: TranslatorAPI | None = None
_summarizer: Summarizer | None = None
_answer_gen: ManagedGenerator | None = None


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


def _get_answer_gen() -> ManagedGenerator:
    global _answer_gen
    if _answer_gen is None:
        _answer_gen = ManagedGenerator()
    return _answer_gen


# ── Schemas ──────────────────────────────────────────────────────────────

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


class LLMConfigRequest(BaseModel):
    active_provider: str | None = None
    providers: dict | None = None


# ── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


# ── Translate ────────────────────────────────────────────────────────────

@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    start = time.time()
    if req.use_api:
        result = _get_translator_api().translate(req.text, req.src, req.tgt)
        source = "api"
    else:
        result = _get_translator().translate(req.text, req.src, req.tgt)
        source = "local"
    duration = int((time.time() - start) * 1000)
    logger.info("translate", extra={
        "text_len": len(req.text), "source": source, "duration_ms": duration,
    })
    return TranslateResponse(translated=result, source=source)


# ── Summarize ────────────────────────────────────────────────────────────

@app.post("/summarize")
def summarize(req: SummarizeRequest):
    start = time.time()
    result = _get_summarizer().summarize(
        req.text, req.model, req.system_prompt, req.user_prompt
    )
    duration = int((time.time() - start) * 1000)
    logger.info("summarize", extra={"text_len": len(req.text), "duration_ms": duration})
    return {"summary": result}


# ── Generate ─────────────────────────────────────────────────────────────

@app.post("/generate")
def generate(req: GenerateRequest):
    start = time.time()
    result = _get_answer_gen().generate(req.question, req.context)
    logger.info("generate", extra={"duration_ms": int((time.time() - start) * 1000)})
    return {"answer": result}


# ── /v1/llm/* — Gerenciamento de Provedores ──────────────────────────────

@app.get("/v1/llm/providers")
def list_providers():
    """Lista provedores de LLM disponíveis com metadados."""
    if not llm_manager._initialized:
        llm_manager.initialize()
    return {"providers": llm_manager.list_providers()}


@app.get("/v1/llm/config")
def get_llm_config():
    """Retorna a configuração atual do LLM (provedor ativo + settings)."""
    return config_store.get_llm_config()


@app.post("/v1/llm/config")
def set_llm_config(req: LLMConfigRequest):
    """Atualiza configuração do LLM e (opcionalmente) troca o provedor ativo."""
    current = config_store.get_llm_config()
    if req.providers is not None:
        current["providers"].update(req.providers)
    if req.active_provider is not None:
        current["active_provider"] = req.active_provider
        provider_cfg = current.get("providers", {}).get(req.active_provider, {})
        if not llm_manager._initialized:
            llm_manager.initialize()
        llm_manager.switch_provider(req.active_provider, provider_cfg)
    config_store.set_llm_config(current)
    return {"status": "ok", "config": current}


@app.post("/v1/llm/test")
def test_llm():
    """Testa conectividade com o provedor ativo."""
    if not llm_manager._initialized:
        llm_manager.initialize()
    result = llm_manager.generate("Say 'ok' and nothing else.", max_tokens=10)
    success = "Erro" not in result and "ok" in result.lower()
    return {"success": success, "response": result}
