import pytest
from PIL import Image, ImageDraw, ImageFont

from src.ocr.engine import OCREngine


@pytest.fixture
def text_image():
    img = Image.new("L", (200, 40), color=255)
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Hello World", fill=0)
    return img


class TestOCREngine:
    def test_extract_text_returns_string(self, text_image):
        engine = OCREngine()
        result = engine.extract_text(text_image)
        assert isinstance(result, str)

    def test_extract_text_empty_on_blank(self):
        engine = OCREngine()
        blank = Image.new("L", (100, 30), color=255)
        result = engine.extract_text(blank)
        assert result == ""
