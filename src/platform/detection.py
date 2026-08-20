"""Detecção de plataforma, sessão e capacidades.

Não importa nenhuma biblioteca pesada — apenas stdlib — para ser seguro
de carregar em qualquer ambiente. As decisões tomadas aqui são usadas
por ``selector.py`` e por toda a UI.
"""
from __future__ import annotations

import enum
import os
import shutil
import sys
from dataclasses import dataclass


class OSType(str, enum.Enum):
    """Sistema operacional detectado."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class SessionType(str, enum.Enum):
    """Tipo de sessão gráfica (aplicável principalmente em Linux)."""

    WAYLAND = "wayland"
    X11 = "x11"
    """Sessão X11 — funciona com mss e captura tradicional."""

    WINDOWS = "windows"
    """Sessão Windows — GDI/Direct3D via mss."""

    UNKNOWN = "unknown"
    """Sessão não detectada (headless, SSH, etc.)."""


@dataclass(frozen=True)
class PlatformCapabilities:
    """Capacidades suportadas na plataforma atual.

    Atributos imutáveis. Use ``detect_capabilities()`` para construir.

    Attributes:
        os: Sistema operacional detectado.
        session: Tipo de sessão gráfica.
        supports_windows_live_captions: True apenas em Windows.
        supports_system_audio_capture: True se o backend consegue capturar
            áudio de saída do sistema (loopback WASAPI no Windows,
            monitor PipeWire no Linux).
        supports_screen_capture: True se a captura de tela é funcional.
            Em Wayland sem portal, é False.
        supports_portal_screen_capture: True se xdg-desktop-portal
            parece instalado (apenas informativo — não garante permissão).
        pipewire_available: PipeWire instalado e em execução.
        pulseaudio_available: PulseAudio disponível (fallback).
    """

    os: OSType
    session: SessionType
    supports_windows_live_captions: bool
    supports_system_audio_capture: bool
    supports_screen_capture: bool
    supports_portal_screen_capture: bool
    pipewire_available: bool
    pulseaudio_available: bool

    @property
    def is_linux(self) -> bool:
        return self.os == OSType.LINUX

    @property
    def is_windows(self) -> bool:
        return self.os == OSType.WINDOWS

    @property
    def is_wayland(self) -> bool:
        return self.session == SessionType.WAYLAND

    @property
    def is_x11(self) -> bool:
        return self.session == SessionType.X11


# ---------------------------------------------------------------------------
# Detecção
# ---------------------------------------------------------------------------

def detect_os() -> OSType:
    """Detecta o sistema operacional via ``sys.platform``.

    Não usa ``platform.system()`` para evitar chamadas de subprocesso
    em ambientes restritos.
    """
    if sys.platform.startswith("win"):
        return OSType.WINDOWS
    if sys.platform.startswith("linux"):
        return OSType.LINUX
    if sys.platform == "darwin":
        return OSType.MACOS
    return OSType.UNKNOWN


def detect_session_type() -> SessionType:
    """Detecta o tipo de sessão gráfica atual.

    Em Linux, lê ``XDG_SESSION_TYPE`` ( Wayland | x11 | tty | unknown).
    Em Windows, retorna sempre ``WINDOWS``. Em macOS, retorna ``UNKNOWN``
    (não suportado para captura especial).
    """
    os_type = detect_os()
    if os_type == OSType.WINDOWS:
        return SessionType.WINDOWS

    xdg = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if xdg == "wayland":
        return SessionType.WAYLAND
    if xdg == "x11":
        return SessionType.X11
    # Heurística de fallback: WAYLAND_DISPLAY presente => Wayland
    if os.environ.get("WAYLAND_DISPLAY"):
        return SessionType.WAYLAND
    if os.environ.get("DISPLAY"):
        return SessionType.X11
    return SessionType.UNKNOWN


def _check_pipewire_running() -> bool:
    """Verifica se PipeWire está rodando (sem exigir bindings Python).

    Estratégia: checar ``pw-cli`` no PATH e versão do socket. Não
    dependemos de ``pygobject`` para a detecção.
    """
    if not shutil.which("pw-cli"):
        return False
    # Checagem rápida do socket — sem bloquear
    socket_path = os.environ.get("PIPEWIRE_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/run/user/0"), "pipewire-0"
    )
    return os.path.exists(socket_path)


def _check_pulseaudio() -> bool:
    """Verifica se PulseAudio (ou compatível) está disponível."""
    return bool(shutil.which("pactl") or shutil.which("pacmd"))


def _check_portal() -> bool:
    """Verifica se xdg-desktop-portal parece instalado."""
    return bool(
        shutil.which("xdg-desktop-portal")
        or shutil.which("gnome-screen-cast")
        or shutil.which("plasmashell")
    )


def detect_capabilities() -> PlatformCapabilities:
    """Constrói ``PlatformCapabilities`` a partir do ambiente atual.

    Esta função nunca lança exceção — sempre retorna um objeto válido,
    mesmo em ambientes headless ou desconhecidos.
    """
    os_type = detect_os()
    session = detect_session_type()

    pipewire = _check_pipewire_running() if os_type == OSType.LINUX else False
    pulseaudio = _check_pulseaudio() if os_type == OSType.LINUX else False
    portal = _check_portal() if os_type == OSType.LINUX else False

    if os_type == OSType.WINDOWS:
        return PlatformCapabilities(
            os=os_type,
            session=session,
            supports_windows_live_captions=True,
            supports_system_audio_capture=True,
            supports_screen_capture=True,
            supports_portal_screen_capture=False,
            pipewire_available=False,
            pulseaudio_available=False,
        )

    if os_type == OSType.LINUX:
        # Em Linux, áudio do sistema requer PipeWire (com monitor) ou
        # PulseAudio com módulo loopback. Microfone funciona sempre que
        # há um servidor de som ativo.
        sys_audio = pipewire or pulseaudio
        # Captura de tela:
        #   X11 — mss funciona.
        #   Wayland — apenas via portal ScreenCast (não implementado aqui
        #     de forma robusta); marcamos como não suportado por padrão.
        if session == SessionType.X11:
            screen = True
        elif session == SessionType.WAYLAND:
            screen = False  # requer portal; não implementado
        else:
            screen = False
        return PlatformCapabilities(
            os=os_type,
            session=session,
            supports_windows_live_captions=False,
            supports_system_audio_capture=sys_audio,
            supports_screen_capture=screen,
            supports_portal_screen_capture=portal,
            pipewire_available=pipewire,
            pulseaudio_available=pulseaudio,
        )

    # macOS / desconhecido
    return PlatformCapabilities(
        os=os_type,
        session=session,
        supports_windows_live_captions=False,
        supports_system_audio_capture=False,
        supports_screen_capture=False,
        supports_portal_screen_capture=False,
        pipewire_available=False,
        pulseaudio_available=False,
    )
