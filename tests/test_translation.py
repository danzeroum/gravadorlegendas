from src.translation.base import Translator
from src.translation.marianmt import TranslatorMarianMT


class TestTranslatorBase:
    def test_abstract_cannot_instantiate(self):
        import pytest

        with pytest.raises(TypeError):
            Translator()  # type: ignore


class TestTranslatorMarianMT:
    def test_translate_empty_returns_empty(self):
        t = TranslatorMarianMT()
        assert t.translate("") == ""

    def test_translate_whitespace_returns_empty(self):
        t = TranslatorMarianMT()
        assert t.translate("   ") == ""

    def test_is_loaded_starts_false(self):
        t = TranslatorMarianMT()
        assert t.is_loaded is False
