"""Ativação das Legendas ao Vivo do Windows via atalho de teclado.

Esta função só é invocada em Windows. Em outras plataformas, o chamador
(``src.caption.windows_live.WindowsLiveCaptionsSource``) nem sequer a
importa — mas mantemos o módulo defensivo para evitar ``AttributeError``
em testes ou em fluxos legados que ainda tentem chamar a função.
"""
from __future__ import annotations

import sys


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def activate_windows_captions() -> bool:
    """Ativa as Legendas do Windows usando Win+Ctrl+L.

    Returns:
        True se o atalho foi enviado; False se a plataforma não é Windows.

    Note:
        Não lança exceção em Linux — apenas retorna False e registra um
        aviso. O fluxo Linux nunca deve chamar esta função; em vez disso,
        usa ``LocalSTTSource``.
    """
    if not _is_windows():
        # Import tardio para evitar ciclo com logging.
        import warnings
        warnings.warn(
            "activate_windows_captions() chamado em plataforma não-Windows; "
            "use LocalSTTSource em Linux.",
            stacklevel=2,
        )
        return False

    import ctypes  # type: ignore[import-not-found]

    # VK_LWIN=0x5B, VK_CONTROL=0x11, VK_L=0x4C, KEYEVENTF_KEYUP=0x0002
    ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
    return True
