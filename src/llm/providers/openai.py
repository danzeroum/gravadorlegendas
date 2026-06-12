from openai import OpenAI

from src.config import settings
from src.llm.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """Provedor OpenAI (GPT-3.5, GPT-4, etc.)."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-3.5-turbo"):
        self._api_key = api_key or settings.openai_api_key
        self._model = model
        self._client = OpenAI(api_key=self._api_key) if self._api_key else None

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        if not self._client:
            return "[Erro: API key OpenAI não configurada]"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._client.chat.completions.create(
                model=kwargs.get("model", self._model),
                messages=messages,
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 500),
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Erro OpenAI: {e}]"

    def get_model_info(self) -> dict:
        return {"provider": "openai", "model": self._model, "has_key": bool(self._api_key)}
