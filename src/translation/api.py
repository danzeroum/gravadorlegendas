from openai import OpenAI
import requests

from src.config import settings
from src.translation.base import Translator


class TranslatorAPI(Translator):
    def __init__(self):
        self._openai_client: OpenAI | None = None
        self._deepseek_key: str = settings.deepseek_api_key

    def _get_openai(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def translate(self, text: str, src: str = "eng", tgt: str = "por") -> str:
        if not text.strip():
            return ""

        if settings.has_openai:
            return self._translate_openai(text, src, tgt)
        if settings.has_deepseek:
            return self._translate_deepseek(text, src, tgt)
        return "[Erro: Nenhuma chave de API configurada]"

    def _translate_openai(self, text: str, src: str, tgt: str) -> str:
        try:
            client = self._get_openai()
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": f"Traduza o texto de {src} para {tgt}. "
                        f"Responda apenas com a tradução.",
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Erro API OpenAI: {e}]"

    def _translate_deepseek(self, text: str, src: str, tgt: str) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._deepseek_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": f"Traduza o texto de {src} para {tgt}. "
                    f"Responda apenas com a tradução.",
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 500,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"[Erro API DeepSeek ({resp.status_code})]"
        except Exception as e:
            return f"[Erro conexão DeepSeek: {e}]"
