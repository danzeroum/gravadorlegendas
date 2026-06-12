import json
import base64

import requests

from src.config import settings
from src.llm.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """Provedor Ollama remoto (VPS) com Basic Auth e streaming NDJSON.

    Credenciais lidas de settings (que carrega do .env).
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        usr = username or settings.ollama_username
        pwd = password or settings.ollama_password
        self._auth_header = self._build_auth(usr, pwd)

    @staticmethod
    def _build_auth(username: str, password: str) -> str | None:
        if not username or not password:
            return None
        raw = f"{username}:{password}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("utf-8")

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        url = f"{self._base_url}/api/generate"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        payload = {
            "model": kwargs.get("model", self._model),
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", 0.3),
                "num_predict": kwargs.get("max_tokens", 500),
            },
        }

        try:
            with requests.post(
                url, headers=headers, json=payload, stream=True, timeout=120
            ) as r:
                r.raise_for_status()
                chunks: list[str] = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = json.loads(line)
                    if "response" in data:
                        chunks.append(data["response"])
                    if data.get("done"):
                        break
                return "".join(chunks).strip()
        except requests.RequestException as e:
            return f"[Erro Ollama: {e}]"
        except json.JSONDecodeError as e:
            return f"[Erro Ollama: resposta inválida - {e}]"
        except Exception as e:
            return f"[Erro Ollama: {e}]"

    def get_model_info(self) -> dict:
        return {
            "provider": "ollama",
            "model": self._model,
            "base_url": self._base_url,
            "auth": bool(self._auth_header),
        }
