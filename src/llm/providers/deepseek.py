import requests

from src.config import settings
from src.llm.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """Provedor DeepSeek via API REST."""

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str = "deepseek-chat"):
        self._api_key = api_key or settings.deepseek_api_key
        self._model = model

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        if not self._api_key:
            return "[Erro: API key DeepSeek não configurada]"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 500),
        }
        try:
            resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"[Erro DeepSeek ({resp.status_code})]"
        except Exception as e:
            return f"[Erro conexão DeepSeek: {e}]"

    def get_model_info(self) -> dict:
        return {"provider": "deepseek", "model": self._model, "has_key": bool(self._api_key)}
