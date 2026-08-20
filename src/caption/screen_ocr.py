"""Fonte: OCR de uma região da tela.

Funciona em X11 e Windows (via ``mss``). Em Wayland, a construção falha
com mensagem clara orientando o usuário a usar X11 ou instalar portal.
"""
from __future__ import annotations

from src.caption.base import CaptionSourceBase, CaptionSourceError
from src.platform.detection import detect_capabilities
from src.platform.selector import select_screen_capture_backend, BackendSelectionError


class ScreenOCRSource(CaptionSourceBase):
    """Fonte de legendas via OCR da tela.

    A captura em si é delegada a ``src.capture.screen_capture.ScreenCapture``.
    Esta classe existe apenas para satisfazer o contrato ``CaptionSource``
    quando o usuário escolhe explicitamente ``screen_ocr`` como modo.
    """

    def __init__(self, region: dict | None = None) -> None:
        super().__init__(name="screen_ocr")
        caps = detect_capabilities()
        try:
            select_screen_capture_backend("auto", caps)
        except BackendSelectionError as e:
            raise CaptionSourceError(str(e)) from e

        from src.capture.screen_capture import ScreenCapture
        from src.config import settings
        self._screen = ScreenCapture(region or settings.screen_region)

    def _start(self) -> None:
        # A captura é por chamada; não há thread própria aqui.
        # O loop de captura fica em ``SessionManager``.
        pass

    def _stop(self) -> None:
        pass

    @property
    def screen_capture(self):
        """Expõe o ScreenCapture para o SessionManager."""
        return self._screen
