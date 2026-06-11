import ctypes


def activate_windows_captions():
    ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x4C, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
    ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
