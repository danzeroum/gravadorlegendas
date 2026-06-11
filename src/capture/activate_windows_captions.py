"""Ativação das legendas do Windows via atalho de teclado."""
import ctypes


def activate_windows_captions():
    """Ativa as Legendas do Windows usando Win+Ctrl+L.

    Simula o pressionamento das teclas Windows, Ctrl e L
    para ativar o recurso de legendas do sistema.
    """
    ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
