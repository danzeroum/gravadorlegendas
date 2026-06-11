from abc import ABC, abstractmethod


class Translator(ABC):
    @abstractmethod
    def translate(self, text: str, src: str = "eng", tgt: str = "por") -> str:
        ...
