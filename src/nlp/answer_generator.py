from abc import ABC, abstractmethod

from src.llm.manager import llm_manager


class AnswerGenerator(ABC):
    """Interface para geração de respostas (Strategy Pattern)."""

    @abstractmethod
    def generate(self, question: str, context: str) -> str:
        """Gera uma resposta em Globish para a pergunta no contexto da reunião."""


class ManagedGenerator(AnswerGenerator):
    """Geração via LLMManager (usa o provedor ativo configurado)."""

    SYSTEM_PROMPT = (
        "You are a helpful meeting assistant. Answer in Globish: "
        "use simple English, short sentences, basic vocabulary."
    )

    def generate(self, question: str, context: str) -> str:
        prompt = (
            f"Meeting context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer (Globish):"
        )
        return llm_manager.generate(prompt, system_prompt=self.SYSTEM_PROMPT)


class LocalGenerator(AnswerGenerator):
    """Wrapper para compatibilidade — delega ao ManagedGenerator."""

    def generate(self, question: str, context: str) -> str:
        return ManagedGenerator().generate(question, context)


class APIGenerator(AnswerGenerator):
    """Wrapper para compatibilidade — delega ao ManagedGenerator."""

    def generate(self, question: str, context: str) -> str:
        return ManagedGenerator().generate(question, context)
