"""Camada de abstração de plataforma.

Centraliza a detecção de sistema operacional, tipo de sessão (X11/Wayland)
e capacidades disponíveis. É o ÚNICO ponto do projeto que decide qual backend
deve ser usado — todo o restante do código consome essas decisões através de
``PlatformCapabilities`` e ``select_*`` helpers.

Submódulos:
    detection.py  — detecta OS / sessão / capacidades
    types.py      — dataclasses e Protocol para backends
    selector.py   — seleciona backends de áudio, tela e legendas
"""
from src.platform.detection import (
    PlatformCapabilities,
    SessionType,
    OSType,
    detect_capabilities,
    detect_os,
    detect_session_type,
)
from src.platform.selector import (
    select_audio_backend,
    select_caption_source,
    select_screen_capture_backend,
    BackendSelectionError,
)

__all__ = [
    "PlatformCapabilities",
    "SessionType",
    "OSType",
    "detect_capabilities",
    "detect_os",
    "detect_session_type",
    "select_audio_backend",
    "select_caption_source",
    "select_screen_capture_backend",
    "BackendSelectionError",
]
