"""Módulo de OCR usando pytesseract."""
import pytesseract
from PIL import Image

from src.config import settings


class OCREngine:
    """Wrapper para o Tesseract OCR.

    Encapsula a chamada ao pytesseract com configuração
    de caminho do executável e idioma.
    """

    def __init__(self):
        """Configura o caminho do Tesseract a partir das settings."""
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path

    def extract_text(self, img: Image.Image, lang: str | None = None) -> str:
        """Extrai texto de uma imagem usando OCR.

        Args:
            img: Imagem PIL pré-processada.
            lang: Código do idioma (ex.: 'eng', 'por'). Se None,
                  usa o idioma padrão das settings.

        Returns:
            String com o texto extraído (vazia se nada encontrado).
        """
        return pytesseract.image_to_string(
            img, lang=lang or settings.ocr_language
        ).strip()
