"""Leitores de frame. ``TesseractReader`` roda 100% local."""
from __future__ import annotations

from typing import Protocol

import numpy as np
from PIL import Image, ImageOps

from src.screen_extract.checkbox import detect_checkbox
from src.screen_extract.models import Linha

MIN_CONF = 30        # confiança mínima por palavra (0..100)
UPSCALE = 2          # texto pequeno rende melhor ampliado


class ReaderError(RuntimeError):
    """Tesseract ausente ou idioma não instalado."""


class FrameReader(Protocol):
    def read(self, img: Image.Image) -> list[Linha]: ...


def normalize_for_ocr(img: Image.Image) -> tuple[Image.Image, np.ndarray]:
    """Cinza, tema escuro invertido; devolve (imagem p/ OCR ampliada, cinza original)."""
    gray = img.convert("L")
    if np.asarray(gray).mean() < 110:
        gray = ImageOps.invert(gray)
    big = gray.resize((gray.width * UPSCALE, gray.height * UPSCALE), Image.LANCZOS)
    return ImageOps.autocontrast(big), np.asarray(gray)


class TesseractReader:
    """OCR com Tesseract (``pytesseract``) + detecção de caixas marcadas."""

    def __init__(self, lang: str = "por", tesseract_cmd: str | None = None):
        try:
            import pytesseract
        except ImportError as e:
            raise ReaderError("pytesseract não instalado (pip install pytesseract).") from e
        if tesseract_cmd is None:
            from src.config import settings
            tesseract_cmd = settings.tesseract_path
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._pt = pytesseract
        self.lang = lang
        self.check()

    def check(self) -> None:
        try:
            langs = self._pt.get_languages(config="")
        except Exception as e:
            raise ReaderError(
                "Tesseract não encontrado. Instale (Fedora: sudo dnf install "
                "tesseract tesseract-langpack-por; Debian/Ubuntu: apt install "
                "tesseract-ocr tesseract-ocr-por) ou ajuste TESSERACT_PATH.") from e
        missing = [lang for lang in self.lang.split("+") if lang not in langs]
        if missing:
            raise ReaderError(f"Idioma(s) do Tesseract ausente(s): {', '.join(missing)}. "
                              "Instale o pacote de idioma (ex.: tesseract-langpack-por).")

    def read(self, img: Image.Image) -> list[Linha]:
        prepared, gray = normalize_for_ocr(img)
        data = self._pt.image_to_data(prepared, lang=self.lang,
                                      output_type=self._pt.Output.DICT)
        groups: dict[tuple[int, int, int], list[int]] = {}
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if conf < MIN_CONF:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            groups.setdefault(key, []).append(i)

        linhas = []
        for idx in groups.values():
            idx.sort(key=lambda i: data["left"][i])
            # O Tesseract lê a própria caixa como símbolo ("[|", "O"…): fora do
            # texto, para a caixa ficar à esquerda da linha e ser detectada.
            while len(idx) > 1 and not any(c.isalnum() for c in data["text"][idx[0]]):
                idx.pop(0)
            x0 = min(data["left"][i] for i in idx)
            y0 = min(data["top"][i] for i in idx)
            x1 = max(data["left"][i] + data["width"][i] for i in idx)
            y1 = max(data["top"][i] + data["height"][i] for i in idx)
            x, y = x0 // UPSCALE, y0 // UPSCALE
            w, h = (x1 - x0) // UPSCALE, (y1 - y0) // UPSCALE
            texto = " ".join(data["text"][i].strip() for i in idx)
            linhas.append(Linha(texto, x, y, w, h, detect_checkbox(gray, x, y, w, h)))
        linhas.sort(key=lambda ln: (ln.y, ln.x))
        return linhas
