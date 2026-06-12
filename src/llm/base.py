from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Interface para provedores de LLM (Strategy Pattern)."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """Gera texto a partir de um prompt."""

    @abstractmethod
    def get_model_info(self) -> dict:
        """Metadados do modelo/configuração atual."""
