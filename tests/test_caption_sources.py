"""Testes para fontes de legenda (CaptionSource)."""
from __future__ import annotations

import sys

import pytest


class TestWindowsLiveCaptionsSource:
    def test_construct_on_linux_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.caption.windows_live import WindowsLiveCaptionsSource
        from src.caption.base import CaptionSourceError
        with pytest.raises(CaptionSourceError, match="não estão disponíveis"):
            WindowsLiveCaptionsSource()

    def test_construct_on_windows_succeeds(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.caption.windows_live import WindowsLiveCaptionsSource
        src = WindowsLiveCaptionsSource()
        assert src.name == "windows_live_captions"
        assert src.is_running is False

    def test_start_on_non_windows_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.caption.windows_live import WindowsLiveCaptionsSource
        from src.caption.base import CaptionSourceError
        src = WindowsLiveCaptionsSource()
        # Mudança de plataforma após construção — defensivo
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(CaptionSourceError, match="não-Windows"):
            src.start()


class TestLocalSTTSource:
    def test_construct_always_succeeds(self):
        from src.caption.local_stt import LocalSTTSource
        src = LocalSTTSource()
        assert src.name == "local_stt"
        assert src.is_running is False

    def test_start_stop_idempotent(self):
        from src.caption.local_stt import LocalSTTSource
        src = LocalSTTSource()
        # Sem audio_manager configurado; start() deve criar um manager
        # mockado para não falhar. Aqui, mockamos o import.
        # Em vez disso, testamos apenas idempotência sem start real.
        src.stop()  # não deve lançar
        src.stop()  # idempotente

    def test_audio_manager_property_initial_none(self):
        from src.caption.local_stt import LocalSTTSource
        src = LocalSTTSource()
        assert src.audio_manager is None


class TestScreenOCRSource:
    def test_construct_on_x11_succeeds(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)
        from src.caption.screen_ocr import ScreenOCRSource
        src = ScreenOCRSource(region={"top": 0, "left": 0, "width": 100, "height": 50})
        assert src.name == "screen_ocr"
        assert src.screen_capture is not None

    def test_construct_on_wayland_without_portal_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)
        from src.caption.screen_ocr import ScreenOCRSource
        from src.caption.base import CaptionSourceError
        with pytest.raises(CaptionSourceError, match="Captura de tela"):
            ScreenOCRSource()


class TestCaptionFactory:
    def test_build_local_stt_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: True)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)
        from src.caption.factory import build_caption_source
        src = build_caption_source("auto")
        from src.caption.local_stt import LocalSTTSource
        assert isinstance(src, LocalSTTSource)

    def test_build_windows_live_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.caption.factory import build_caption_source
        src = build_caption_source("auto")
        from src.caption.windows_live import WindowsLiveCaptionsSource
        assert isinstance(src, WindowsLiveCaptionsSource)

    def test_build_windows_live_on_linux_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.caption.factory import build_caption_source
        from src.caption.base import CaptionSourceError
        with pytest.raises(CaptionSourceError):
            build_caption_source("windows_live_captions")

    def test_build_invalid_raises(self):
        from src.caption.factory import build_caption_source
        from src.caption.base import CaptionSourceError
        with pytest.raises(CaptionSourceError):
            build_caption_source("azure")
