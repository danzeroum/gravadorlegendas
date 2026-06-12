from src.config import settings
from src.llm.base import BaseLLMProvider


class LocalGGUFProvider(BaseLLMProvider):
    """Provedor local via llama-cpp-python (GGUF). Opcional."""

    def __init__(self, model_path: str | None = None, n_ctx: int = 2048, n_threads: int = 4):
        self._model_path = model_path or settings.local_llm_path
        self._n_ctx = n_ctx or settings.llm_ctx
        self._n_threads = n_threads or settings.llm_threads
        self._llm = None

    def _load(self):
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                verbose=False,
            )
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python não instalado. "
                "Execute: pip install llama-cpp-python"
            )
        except Exception as e:
            raise RuntimeError(f"Falha ao carregar GGUF: {e}")

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        self._load()
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        try:
            output = self._llm(
                full_prompt,
                max_tokens=kwargs.get("max_tokens", 150),
                temperature=kwargs.get("temperature", 0.2),
                stop=kwargs.get("stop", ["\n\n"]),
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            return f"[Erro LLM local: {e}]"

    def get_model_info(self) -> dict:
        return {
            "provider": "local_gguf",
            "model_path": self._model_path,
            "n_ctx": self._n_ctx,
            "loaded": self._llm is not None,
        }
