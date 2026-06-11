from transformers import MarianMTModel, MarianTokenizer

from src.config import settings
from src.translation.base import Translator


class TranslatorMarianMT(Translator):
    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or settings.translation_model
        self._tokenizer: MarianTokenizer | None = None
        self._model: MarianMTModel | None = None

    def _load(self):
        if self._model is not None:
            return
        self._tokenizer = MarianTokenizer.from_pretrained(self._model_name)
        self._model = MarianMTModel.from_pretrained(self._model_name)

    def translate(self, text: str, src: str = "eng", tgt: str = "por") -> str:
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
        return self._model is not None
