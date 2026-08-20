"""Fábrica de fontes de legenda.

Centraliza a construção com base na seleção automática de plataforma.
"""
from __future__ import annotations

from src.caption.base import CaptionSourceBase, CaptionSourceError
from src.platform.detection import detect_capabilities
from src.platform.selector import select_caption_source, BackendSelectionError


def build_caption_source(
    requested: str = "auto",
    **kwargs,
) -> CaptionSourceBase:
    """Constrói a fonte de legenda apropriada.

    Args:
        requested: "auto" | "windows_live_captions" | "local_stt" | "screen_ocr".
        **kwargs: Argumentos específicos da fonte (ex.: ``region`` para
            ``screen_ocr``; ``audio_manager`` e callbacks para ``local_stt``).

    Returns:
        Instância concreta de ``CaptionSourceBase``.

    Raises:
        CaptionSourceError: Se a fonte não puder ser construída nesta plataforma.
    """
    caps = detect_capabilities()
    try:
        chosen = select_caption_source(requested, caps)
    except BackendSelectionError as e:
        raise CaptionSourceError(str(e)) from e

    if chosen == "windows_live_captions":
        from src.caption.windows_live import WindowsLiveCaptionsSource
        return WindowsLiveCaptionsSource()

    if chosen == "local_stt":
        from src.caption.local_stt import LocalSTTSource
        return LocalSTTSource(**kwargs)

    if chosen == "screen_ocr":
        from src.caption.screen_ocr import ScreenOCRSource
        return ScreenOCRSource(**kwargs)

    raise CaptionSourceError(f"Fonte de legenda não suportada: {chosen!r}")
