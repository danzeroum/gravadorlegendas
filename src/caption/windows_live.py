"""Fonte: Legendas ao Vivo do Windows.

Ativa o recurso nativo de legendas do Windows 10/11 via atalho
``Win+Ctrl+L``. Em Linux, a construção da fonte já falha com mensagem
clara — o fluxo Linux nunca deve instanciar esta classe.
"""
from __future__ import annotations

import sys

from src.caption.base import CaptionSourceBase, CaptionSourceError
from src.platform.detection import detect_capabilities


class WindowsLiveCaptionsSource(CaptionSourceBase):
    """Ativa Legendas ao Vivo do Windows.

    A ativação em si é não-bloqueante: apenas envia o atalho de teclado.
    A leitura das legendas é feita por OCR da janela de legendas
    (responsabilidade de ``ScreenOCRSource`` quando configurado para tal).
    """

    def __init__(self) -> None:
        super().__init__(name="windows_live_captions")
        caps = detect_capabilities()
        if not caps.supports_windows_live_captions:
            raise CaptionSourceError(
                "Legendas ao Vivo do Windows não estão disponíveis nesta "
                f"plataforma ({caps.os.value}). Use 'local_stt' no lugar."
            )

    def _start(self) -> None:
        # Importação tardia: só carrega o módulo Windows-specific quando
        # realmente necessário (e em Windows).
        if not sys.platform.startswith("win"):
            raise CaptionSourceError(
                "Tentativa de ativar Legendas do Windows em plataforma não-Windows."
            )
        from src.capture.activate_windows_captions import activate_windows_captions

        ok = activate_windows_captions()
        if not ok:
            raise CaptionSourceError(
                "Falha ao enviar atalho Win+Ctrl+L para ativar legendas."
            )

    def _stop(self) -> None:
        # Não há API para "desativar" as legendas — o usuário pode fechá-las
        # manualmente. Mantemos o método para satisfazer o Protocol.
        pass
