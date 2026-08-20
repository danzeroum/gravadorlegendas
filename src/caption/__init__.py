"""Fontes de legenda abstraídas.

Implementa o Protocol ``CaptionSource`` definido em ``src.platform.types``.

Três fontes concretas:

- ``WindowsLiveCaptionsSource`` — ativa Legendas ao Vivo do Windows via
  atalho Win+Ctrl+L. Só funciona em Windows; em Linux lança erro claro.
- ``LocalSTTSource`` — usa o pipeline de áudio + transcrição local
  (faster-whisper) do projeto. Funciona em Windows e Linux.
- ``ScreenOCRSource`` — captura região da tela e faz OCR. Funciona em
  X11 e Windows; em Wayland sem portal, lança erro.

A escolha de qual fonte usar é feita por
``src.platform.selector.select_caption_source``.
"""
from src.caption.base import CaptionSourceBase, CaptionSourceError
from src.caption.windows_live import WindowsLiveCaptionsSource
from src.caption.local_stt import LocalSTTSource
from src.caption.screen_ocr import ScreenOCRSource
from src.caption.factory import build_caption_source

__all__ = [
    "CaptionSourceBase",
    "CaptionSourceError",
    "WindowsLiveCaptionsSource",
    "LocalSTTSource",
    "ScreenOCRSource",
    "build_caption_source",
]
