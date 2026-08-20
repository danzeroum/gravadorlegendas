"""Testes para seleção automática de backends."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from src.platform.detection import (
    OSType,
    PlatformCapabilities,
    SessionType,
)
from src.platform.selector import (
    BackendSelectionError,
    select_audio_backend,
    select_caption_source,
    select_screen_capture_backend,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _caps(
    os=OSType.LINUX,
    session=SessionType.X11,
    *,
    pipewire=True,
    pulseaudio=True,
    portal=False,
    win_live=True,
    sys_audio=True,
    screen=True,
) -> PlatformCapabilities:
    return PlatformCapabilities(
        os=os,
        session=session,
        supports_windows_live_captions=win_live,
        supports_system_audio_capture=sys_audio,
        supports_screen_capture=screen,
        supports_portal_screen_capture=portal,
        pipewire_available=pipewire,
        pulseaudio_available=pulseaudio,
    )


WINDOWS_CAPS = _caps(
    os=OSType.WINDOWS,
    session=SessionType.WINDOWS,
    pipewire=False,
    pulseaudio=False,
    portal=False,
)


# ---------------------------------------------------------------------------
# Audio backend
# ---------------------------------------------------------------------------

class TestSelectAudioBackend:
    def test_auto_windows(self):
        assert select_audio_backend("auto", WINDOWS_CAPS) == "wasapi"

    def test_auto_linux_pipewire(self):
        assert select_audio_backend("auto", _caps()) == "pipewire"

    def test_auto_linux_pulseaudio_only(self):
        caps = _caps(pipewire=False, pulseaudio=True)
        assert select_audio_backend("auto", caps) == "pipewire"

    def test_auto_linux_no_audio_server_raises(self):
        caps = _caps(pipewire=False, pulseaudio=False, sys_audio=False)
        with pytest.raises(BackendSelectionError, match="Nenhum servidor de áudio"):
            select_audio_backend("auto", caps)

    def test_explicit_wasapi_windows(self):
        assert select_audio_backend("wasapi", WINDOWS_CAPS) == "wasapi"

    def test_wasapi_on_linux_raises(self):
        with pytest.raises(BackendSelectionError, match="só é suportado no Windows"):
            select_audio_backend("wasapi", _caps())

    def test_pipewire_on_windows_raises(self):
        with pytest.raises(BackendSelectionError, match="não é suportado no Windows"):
            select_audio_backend("pipewire", WINDOWS_CAPS)

    def test_pipewire_not_running_raises(self):
        caps = _caps(pipewire=False, pulseaudio=False, sys_audio=False)
        with pytest.raises(BackendSelectionError, match="PipeWire não está rodando"):
            select_audio_backend("pipewire", caps)

    def test_invalid_value_raises(self):
        with pytest.raises(BackendSelectionError, match="inválido"):
            select_audio_backend("alsa", _caps())

    def test_unknown_os_raises(self):
        caps = _caps(os=OSType.UNKNOWN, session=SessionType.UNKNOWN,
                     pipewire=False, pulseaudio=False, sys_audio=False, screen=False)
        with pytest.raises(BackendSelectionError):
            select_audio_backend("auto", caps)


# ---------------------------------------------------------------------------
# Caption source
# ---------------------------------------------------------------------------

class TestSelectCaptionSource:
    def test_auto_windows(self):
        assert select_caption_source("auto", WINDOWS_CAPS) == "windows_live_captions"

    def test_auto_linux(self):
        assert select_caption_source("auto", _caps()) == "local_stt"

    def test_windows_live_on_windows(self):
        assert (
            select_caption_source("windows_live_captions", WINDOWS_CAPS)
            == "windows_live_captions"
        )

    def test_windows_live_on_linux_raises(self):
        with pytest.raises(BackendSelectionError, match="não estão disponíveis"):
            select_caption_source("windows_live_captions", _caps(win_live=False))

    def test_local_stt_always_ok(self):
        assert select_caption_source("local_stt", WINDOWS_CAPS) == "local_stt"
        assert select_caption_source("local_stt", _caps()) == "local_stt"

    def test_screen_ocr_x11(self):
        assert select_caption_source("screen_ocr", _caps(session=SessionType.X11)) == "screen_ocr"

    def test_screen_ocr_wayland_raises(self):
        caps = _caps(session=SessionType.WAYLAND, screen=False)
        with pytest.raises(BackendSelectionError, match="Captura de tela indisponível"):
            select_caption_source("screen_ocr", caps)

    def test_invalid_value_raises(self):
        with pytest.raises(BackendSelectionError, match="inválido"):
            select_caption_source("azure", _caps())


# ---------------------------------------------------------------------------
# Screen capture backend
# ---------------------------------------------------------------------------

class TestSelectScreenCaptureBackend:
    def test_auto_windows(self):
        assert select_screen_capture_backend("auto", WINDOWS_CAPS) == "mss"

    def test_auto_x11(self):
        assert select_screen_capture_backend("auto", _caps(session=SessionType.X11)) == "mss"

    def test_auto_wayland_with_portal(self):
        caps = _caps(session=SessionType.WAYLAND, screen=False, portal=True)
        assert select_screen_capture_backend("auto", caps) == "portal"

    def test_auto_wayland_without_portal_raises(self):
        caps = _caps(session=SessionType.WAYLAND, screen=False, portal=False)
        with pytest.raises(BackendSelectionError, match="xdg-desktop-portal não está"):
            select_screen_capture_backend("auto", caps)

    def test_explicit_mss_on_wayland_raises(self):
        caps = _caps(session=SessionType.WAYLAND, screen=False, portal=True)
        with pytest.raises(BackendSelectionError, match="não funciona em Wayland"):
            select_screen_capture_backend("mss", caps)

    def test_portal_without_xdg_raises(self):
        caps = _caps(portal=False)
        with pytest.raises(BackendSelectionError, match="requer xdg-desktop-portal"):
            select_screen_capture_backend("portal", caps)

    def test_invalid_value_raises(self):
        with pytest.raises(BackendSelectionError, match="inválido"):
            select_screen_capture_backend("gnome-screenshot", _caps())
