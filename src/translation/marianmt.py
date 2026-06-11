"""Tradutor local usando MarianMT (Hugging Face Transformers)."""
from transformers import MarianMTModel, MarianTokenizer

from src.config import settings
from src.translation.base import Translator


class TranslatorMarianMT(Translator):
    """Tradução local com modelos MarianMT.

    Carrega o modelo sob demanda (lazy loading) e suporta
    qualquer par de idiomas disponível no Hugging Face.

    Attributes:
        is_loaded: Indica se o modelo já foi carregado em memória.
    """

    def __init__(self, model_name: str | None = None):
        """Inicializa o tradutor com o nome do modelo.

        Args:
            model_name: Nome do modelo no Hugging Face. Se None,
                        usa o valor das settings.
        """
        self._model_name = model_name or settings.translation_model
        self._tokenizer: MarianTokenizer | None = None
        self._model: MarianMTModel | None = None

    def _load(self):
        """Carrega o modelo e tokenizer em memória (lazy)."""
        if self._model is not None:
            return
        self._tokenizer = MarianTokenizer.from_pretrained(self._model_name)
        self._model = MarianMTModel.from_pretrained(self._model_name)

    def translate(self, text: str, src: str = "eng", tgt: str = "por") -> str:
        """Traduz texto usando o modelo MarianMT.

        Args:
            text: Texto a traduzir.
            src: Código do idioma de origem (não usado pelo MarianMT).
            tgt: Código do idioma de destino (ex.: 'por').

        Returns:
            Texto traduzido ou mensagem de erro.
        """
        if not text.strip():
            return ""
        self._load()
        try:
            text_with_token = f">>{tgt}<< {text}"
            inputs = self._tokenizer(
                [text_with_token], return_tensors="pt", padding=True, truncation=True
            )
            translated = self._model.generate(**inputs)
            return self._tokenizer.decode(translated[0], skip_special_tokens=True)
        except Exception as e:
            return f"[Erro tradução: {e}]"

    @property
    def is_loaded(self) -> bool:
        """Indica se o modelo já foi carregado."""
        return self._model is not None
