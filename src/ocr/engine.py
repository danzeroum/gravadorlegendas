import pytesseract
from PIL import Image

from src.config import settings


class OCREngine:
    def __init__(self):
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path

    def extract_text(self, img: Image.Image, lang: str | None = None) -> str:
        return pytesseract.image_to_string(
            img, lang=lang or settings.ocr_language
        ).strip()
