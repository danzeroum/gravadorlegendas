"""Geração de respostas Globish usando LLM local ou API."""
from abc import ABC, abstractmethod

import requests

from src.config import settings


class AnswerGenerator(ABC):
    """Interface para geração de respostas (Strategy Pattern)."""

    @abstractmethod
    def generate(self, question: str, context: str) -> str:
        """Gera uma resposta em Globish para a pergunta no contexto da reunião.

        Args:
            question: Pergunta detectada.
            context: Contexto da reunião.

        Returns:
            Resposta em Globish (inglês simplificado).
        """


class LocalGenerator(AnswerGenerator):
    """Geração de respostas usando LLM local (llama-cpp-python).

    Carrega o modelo .gguf sob demanda. Requer llama-cpp-python
    e um arquivo de modelo compatível.
    """

    def __init__(self):
        self._llm = None

    def _load(self):
        """Carrega o modelo GGUF (lazy loading)."""
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama

            self._llm = Llama(
                model_path=settings.local_llm_path,
                n_ctx=settings.llm_ctx,
                n_threads=settings.llm_threads,
                verbose=False,
            )
        except Exception as e:
            self._llm = None
            raise RuntimeError(f"Falha ao carregar LLM local: {e}")

    def generate(self, question: str, context: str) -> str:
        """Gera resposta usando o LLM local.

        Args:
            question: Pergunta a responder.
            context: Contexto da reunião.

        Returns:
            Resposta em Globish.
        """
        self._load()
        prompt = (
            f"You are a meeting assistant. Answer in Globish: use simple English, "
            f"short sentences, basic vocabulary.\n"
            f"Meeting context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer (Globish):"
        )
        try:
            output = self._llm(
                prompt, max_tokens=150, temperature=0.2, stop=["Question:", "\n\n"]
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            return f"[Erro LLM local: {e}]"


class APIGenerator(AnswerGenerator):
    """Geração de respostas usando API (OpenAI ou DeepSeek)."""

    def generate(self, question: str, context: str) -> str:
        """Gera resposta via API com fallback automático.

        Tenta OpenAI primeiro, depois DeepSeek.

        Args:
            question: Pergunta a responder.
            context: Contexto da reunião.

        Returns:
            Resposta em Globish.
        """
        if settings.has_openai:
            return self._generate_openai(question, context)
        if settings.has_deepseek:
            return self._generate_deepseek(question, context)
        return "[Erro: Nenhuma chave de API configurada]"

    def _generate_openai(self, question: str, context: str) -> str:
        """Gera resposta via OpenAI."""
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        system_msg = (
            "You are a helpful assistant that answers in Globish: "
            "simple English, short sentences, basic vocabulary."
        )
        user_msg = (
            f"Meeting context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer (Globish):"
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Erro OpenAI: {e}]"

    def _generate_deepseek(self, question: str, context: str) -> str:
        """Gera resposta via DeepSeek."""
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
                    "content": (
                        "You are a helpful assistant that answers in Globish: "
                        "simple English, short sentences, basic vocabulary."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Meeting context:\n{context}\n\n"
                        f"Question: {question}\n\n"
                        f"Answer (Globish):"
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 150,
            "stream": False,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"[Erro API ({resp.status_code})]"
        except Exception as e:
            return f"[Erro conexão API: {e}]"
