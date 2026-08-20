"""Testes para a camada de detecção de plataforma."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from src.platform.detection import (
    OSType,
    SessionType,
    detect_capabilities,
    detect_os,
    detect_session_type,
)


class TestDetectOS:
    def test_windows(self):
        with patch.object(sys, "platform", "win32"):
            assert detect_os() == OSType.WINDOWS

    def test_linux(self):
        with patch.object(sys, "platform", "linux"):
            assert detect_os() == OSType.LINUX

    def test_macos(self):
        with patch.object(sys, "platform", "darwin"):
            assert detect_os() == OSType.MACOS

    def test_unknown(self):
        with patch.object(sys, "platform", "haiku"):
            assert detect_os() == OSType.UNKNOWN


class TestDetectSessionType:
    def test_windows_always_returns_windows(self):
        with patch.object(sys, "platform", "win32"):
            assert detect_session_type() == SessionType.WINDOWS

    def test_linux_wayland(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        monkeypatch.delenv("DISPLAY", raising=False)
        assert detect_session_type() == SessionType.WAYLAND

    def test_linux_x11(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        assert detect_session_type() == SessionType.X11

    def test_linux_wayland_display_only(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.delenv("DISPLAY", raising=False)
        assert detect_session_type() == SessionType.WAYLAND

    def test_linux_display_only(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        assert detect_session_type() == SessionType.X11

    def test_linux_headless(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        assert detect_session_type() == SessionType.UNKNOWN


class TestPlatformCapabilities:
    def test_windows_full_support(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        caps = detect_capabilities()
        assert caps.os == OSType.WINDOWS
        assert caps.supports_windows_live_captions is True
        assert caps.supports_system_audio_capture is True
        assert caps.supports_screen_capture is True
        assert caps.pipewire_available is False

    def test_linux_x11_with_pipewire(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        # Simular PipeWire rodando
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)
        caps = detect_capabilities()
        assert caps.os == OSType.LINUX
        assert caps.session == SessionType.X11
        assert caps.supports_windows_live_captions is False
        assert caps.supports_system_audio_capture is True
        assert caps.supports_screen_capture is True
        assert caps.pipewire_available is True
        assert caps.is_wayland is False
        assert caps.is_x11 is True

    def test_linux_wayland_without_portal(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)
        caps = detect_capabilities()
        assert caps.session == SessionType.WAYLAND
        assert caps.supports_screen_capture is False
        assert caps.supports_portal_screen_capture is False
        assert caps.is_wayland is True

    def test_linux_wayland_with_portal(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: True)
        caps = detect_capabilities()
        assert caps.session == SessionType.WAYLAND
        assert caps.supports_screen_capture is False  # portal ainda não ativa mss
        assert caps.supports_portal_screen_capture is True

    def test_linux_no_audio_server(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: False)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: False)
        caps = detect_capabilities()
        assert caps.supports_system_audio_capture is False

    def test_immutable(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        caps = detect_capabilities()
        with pytest.raises((AttributeError, Exception)):
            caps.os = OSType.LINUX  # type: ignore[misc]
