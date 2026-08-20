"""Seleção automática de backends com sobrescrita por configuração.

Esta é a única função chamada pela UI / managers para escolher qual
backend concreto usar. Implementa fallback gracioso e erros claros.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.platform.detection import (
    OSType,
    PlatformCapabilities,
    SessionType,
    detect_capabilities,
)


class BackendSelectionError(RuntimeError):
    """Erro de seleção de backend — sempre tem mensagem amigável em PT."""


# ---------------------------------------------------------------------------
# Áudio
# ---------------------------------------------------------------------------

VALID_AUDIO_BACKENDS = {"auto", "wasapi", "pipewire"}


def select_audio_backend(
    requested: str = "auto",
    capabilities: PlatformCapabilities | None = None,
) -> str:
    """Seleciona o backend de áudio.

    Args:
        requested: "auto" | "wasapi" | "pipewire".
        capabilities: Plataforma detectada. Se None, detecta automaticamente.

    Returns:
        Nome do backend selecionado: "wasapi" ou "pipewire".

    Raises:
        BackendSelectionError: backend inválido ou incompatível com a plataforma.
    """
    if requested not in VALID_AUDIO_BACKENDS:
        raise BackendSelectionError(
            f"audio_backend inválido: {requested!r}. "
            f"Valores aceitos: {sorted(VALID_AUDIO_BACKENDS)}"
        )

    caps = capabilities or detect_capabilities()

    if requested == "wasapi":
        if caps.os != OSType.WINDOWS:
            raise BackendSelectionError(
                "Backend 'wasapi' só é suportado no Windows. "
                "Use 'pipewire' ou 'auto' em Linux."
            )
        return "wasapi"

    if requested == "pipewire":
        if caps.os == OSType.WINDOWS:
            raise BackendSelectionError(
                "Backend 'pipewire' não é suportado no Windows. "
                "Use 'wasapi' ou 'auto'."
            )
        if not caps.pipewire_available:
            raise BackendSelectionError(
                "PipeWire não está rodando. Verifique o serviço "
                "(systemctl --user status pipewire) e tente novamente."
            )
        return "pipewire"

    # auto
    if caps.os == OSType.WINDOWS:
        return "wasapi"
    if caps.os == OSType.LINUX:
        if caps.pipewire_available:
            return "pipewire"
        if caps.pulseaudio_available:
            # PulseAudio como fallback — o backend PipeWire usa pactl
            # para descoberta e consegue capturar via monitor source.
            return "pipewire"
        raise BackendSelectionError(
            "Nenhum servidor de áudio detectado (PipeWire/PulseAudio). "
            "Instale pipewire ou pulseaudio e reinicie a sessão."
        )
    raise BackendSelectionError(
        f"Sistema operacional {caps.os.value!r} não possui backend de áudio suportado."
    )


# ---------------------------------------------------------------------------
# Legendas
# ---------------------------------------------------------------------------

VALID_CAPTION_SOURCES = {
    "auto",
    "windows_live_captions",
    "local_stt",
    "screen_ocr",
}


def select_caption_source(
    requested: str = "auto",
    capabilities: PlatformCapabilities | None = None,
) -> str:
    """Seleciona a fonte de legendas.

    Args:
        requested: "auto" | "windows_live_captions" | "local_stt" | "screen_ocr".
        capabilities: Plataforma detectada.

    Returns:
        Nome da fonte selecionada.

    Raises:
        BackendSelectionError: fonte incompatível com a plataforma.
    """
    if requested not in VALID_CAPTION_SOURCES:
        raise BackendSelectionError(
            f"caption_source inválido: {requested!r}. "
            f"Valores aceitos: {sorted(VALID_CAPTION_SOURCES)}"
        )

    caps = capabilities or detect_capabilities()

    if requested == "windows_live_captions":
        if not caps.supports_windows_live_captions:
            raise BackendSelectionError(
                "Legendas ao Vivo do Windows não estão disponíveis nesta plataforma. "
                "Use 'local_stt' para transcrição local via Whisper."
            )
        return "windows_live_captions"

    if requested == "local_stt":
        return "local_stt"

    if requested == "screen_ocr":
        if not caps.supports_screen_capture:
            raise BackendSelectionError(
                "Captura de tela indisponível nesta sessão. "
                "Em Wayland, faça logout e entre em sessão X11, ou ative "
                "xdg-desktop-portal com suporte a ScreenCast."
            )
        return "screen_ocr"

    # auto
    if caps.os == OSType.WINDOWS:
        # Windows: legendas ao vivo quando disponível.
        return "windows_live_captions"
    # Linux e outros: usar transcrição local sempre.
    return "local_stt"


# ---------------------------------------------------------------------------
# Captura de tela
# ---------------------------------------------------------------------------

VALID_SCREEN_BACKENDS = {"auto", "mss", "portal"}


def select_screen_capture_backend(
    requested: str = "auto",
    capabilities: PlatformCapabilities | None = None,
) -> str:
    """Seleciona o backend de captura de tela.

    Args:
        requested: "auto" | "mss" | "portal".
        capabilities: Plataforma detectada.

    Returns:
        "mss" (X11/Windows) ou "portal" (Wayland).

    Raises:
        BackendSelectionError: backend incompatível ou sessão sem suporte.
    """
    if requested not in VALID_SCREEN_BACKENDS:
        raise BackendSelectionError(
            f"screen_capture_backend inválido: {requested!r}. "
            f"Valores aceitos: {sorted(VALID_SCREEN_BACKENDS)}"
        )

    caps = capabilities or detect_capabilities()

    if requested == "portal":
        if not caps.supports_portal_screen_capture:
            raise BackendSelectionError(
                "Backend 'portal' requer xdg-desktop-portal instalado e ativo. "
                "Instale xdg-desktop-portal e o backend específico do seu DE "
                "(gnome / kde / sway)."
            )
        return "portal"

    if requested == "mss":
        if caps.session == SessionType.WAYLAND:
            raise BackendSelectionError(
                "Backend 'mss' não funciona em Wayland (captura preta). "
                "Use 'portal' ou faça logout e entre em sessão X11."
            )
        return "mss"

    # auto
    if caps.session == SessionType.WAYLAND:
        if caps.supports_portal_screen_capture:
            return "portal"
        raise BackendSelectionError(
            "Sessão Wayland detectada, mas xdg-desktop-portal não está "
            "disponível. Captura de tela desativada. Alternativas: "
            "(1) faça logout e entre em sessão 'Xorg' no gerenciador de login; "
            "(2) instale xdg-desktop-portal + backend do DE."
        )
    if caps.session in (SessionType.X11, SessionType.WINDOWS):
        return "mss"
    raise BackendSelectionError(
        "Tipo de sessão não suportado para captura de tela: "
        f"{caps.session.value!r}."
    )
