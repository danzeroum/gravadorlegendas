"""Classe abstrata para tradutores (Strategy Pattern)."""
from abc import ABC, abstractmethod


class Translator(ABC):
    """Interface para estratégias de tradução.

    Implementações concretas: TranslatorMarianMT, TranslatorAPI.
    """

    @abstractmethod
    def translate(self, text: str, src: str = "eng", tgt: str = "por") -> str:
        """Traduz o texto de src para tgt.

        Args:
            text: Texto a ser traduzido.
            src: Código do idioma de origem.
            tgt: Código do idioma de destino.

        Returns:
            Texto traduzido.
        """
