from openai import OpenAI
import requests

from src.config import settings


class Summarizer:
    def __init__(self):
        self._openai_client: OpenAI | None = None

    def _get_openai(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def summarize(
        self,
        text: str,
        model: str = "gpt-3.5-turbo",
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> str:
        if not text.strip():
            return "[Erro: texto vazio]"

        if settings.has_openai:
            return self._summarize_openai(text, model, system_prompt, user_prompt)
        if settings.has_deepseek:
            return self._summarize_deepseek(text, system_prompt, user_prompt)
        return "[Erro: Nenhuma chave de API configurada]"

    def _summarize_openai(
        self, text: str, model: str, system_prompt: str | None, user_prompt: str | None
    ) -> str:
        try:
            client = self._get_openai()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                        or "Você é um assistente que resume reuniões.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{user_prompt or 'Por favor, resuma o seguinte texto:'}"
                            f"\n\n{text}"
                        ),
                    },
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Erro ao gerar resumo: {e}]"

    def _summarize_deepseek(
        self, text: str, system_prompt: str | None, user_prompt: str | None
    ) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                    or "Você é um assistente que resume reuniões.",
                },
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt or 'Por favor, resuma o seguinte texto:'}"
                        f"\n\n{text}"
                    ),
                },
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"[Erro DeepSeek ({resp.status_code})]"
        except Exception as e:
            return f"[Erro conexão DeepSeek: {e}]"
