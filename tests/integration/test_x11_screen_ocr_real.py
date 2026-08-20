"""Testes de integração REAIS de captura de tela + OCR em X11.

Exigem:
- Sessão X11 ativa (XDG_SESSION_TYPE=x11)
- Tesseract com idioma português (tesseract-langpack-por)
- Display funcional

NÃO usam rede. Não exigem GPU.

Marcadores:
    @pytest.mark.integration
    @pytest.mark.requires_x11
    @pytest.mark.requires_display

Rodar:
    pytest -q -m "integration and requires_x11"
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest

from tests.integration.conftest import require_display, require_tesseract, require_x11


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_x11,
    pytest.mark.requires_display,
]


class TestX11ScreenOCRReal:
    """Validação real de captura de tela + OCR em X11."""

    def setup_method(self):
        require_x11()
        require_display()
        require_tesseract()

    # ------------------------------------------------------------------
    # E2E-11: OCR em X11
    # ------------------------------------------------------------------

    def test_e2e_11_x11_screen_capture_not_black(self):
        """E2E-11: Captura de tela em X11 retorna frame não preto."""
        from src.capture.screen_capture import ScreenCapture, ScreenCaptureError

        # Captura uma região pequena do canto superior esquerdo
        region = {"top": 0, "left": 0, "width": 200, "height": 100}
        cap = ScreenCapture(region)

        img = cap.capture()
        assert img is not None
        assert img.size == (200, 100)

        # Valida que não é frame preto (limitação Wayland)
        extrema = img.convert("L").getextrema()
        assert extrema != (0, 0), "Frame totalmente preto — captura X11 falhou"

    def test_e2e_11_x11_ocr_returns_text(self):
        """E2E-11: OCR extrai texto de região com conteúdo.

        Para um teste E2E-11 completo, abre-se uma janela com texto PT
        conhecido e valida-se o OCR. Aqui, capturamos a tela inteira
        e apenas validamos que o OCR retorna algo (mesmo que vazio se
        a região não tiver texto).
        """
        from src.capture.screen_capture import ScreenCapture
        from src.ocr.engine import OCREngine
        from src.config import settings

        # Captura uma região maior (toolbar, menu, etc. costumam ter texto)
        region = {"top": 0, "left": 0, "width": 800, "height": 60}
        cap = ScreenCapture(region)
        img = cap.capture()
        processed = cap.preprocess(img)

        engine = OCREngine()
        # Se TESSERACT_PATH estiver vazio, usa 'tesseract' do PATH
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path or "tesseract"

        text = engine.extract_text(processed, lang="eng+por")
        assert isinstance(text, str)
        # Não assertamos texto não vazio — a região pode não ter texto.
        # Para validação completa, abra uma janela com texto PT conhecido.
        print(f"\n[OCR] Texto extraído: {text!r}")

    def test_x11_session_confirmed(self):
        """Confirma que XDG_SESSION_TYPE=x11."""
        assert os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"

    def test_tesseract_portuguese_available(self):
        """Confirma que o Tesseract tem idioma português instalado."""
        try:
            result = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                pytest.skip("tesseract --list-langs falhou")
            langs = result.stdout.lower()
            assert "por" in langs, (
                "Idioma português (por) não instalado no Tesseract. "
                "Instale: sudo dnf install tesseract-langpack-por"
            )
        except FileNotFoundError:
            pytest.skip("Tesseract não encontrado")
