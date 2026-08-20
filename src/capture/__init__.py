"""Módulo de captura de tela e ativação de legendas.

- ``ScreenCapture``: captura região da tela (mss). Funciona em X11 e
  Windows. Em Wayland, lança erro claro quando chamada.
- ``activate_windows_captions``: atalho Win+Ctrl+L. Em Linux, é um
  no-op com aviso (não lança exceção).
"""
from src.capture.screen_capture import ScreenCapture
from src.capture.activate_windows_captions import activate_windows_captions

__all__ = ["ScreenCapture", "activate_windows_captions"]
