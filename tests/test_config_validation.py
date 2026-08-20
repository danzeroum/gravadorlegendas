"""Testes para validação de configuração multiplataforma."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


class TestSettingsDefaults:
    def test_tesseract_path_default_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        # Reimporta para aplicar o default dinâmico
        import importlib
        import src.config as cfg
        importlib.reload(cfg)
        assert "Tesseract" in cfg._default_tesseract_path()

    def test_tesseract_path_default_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        import importlib
        import src.config as cfg
        importlib.reload(cfg)
        assert cfg._default_tesseract_path() == "tesseract"


class TestValidateSettings:
    def _make_settings(self, **overrides):
        from src.config import Settings
        s = Settings()
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def test_valid_auto_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.config import validate_settings
        errors = validate_settings(self._make_settings())
        assert errors == []

    def test_valid_auto_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.config import validate_settings
        errors = validate_settings(self._make_settings())
        assert errors == []

    def test_invalid_audio_backend_value(self):
        from src.config import validate_settings
        s = self._make_settings(audio_backend="alsa")
        errors = validate_settings(s)
        assert any("audio_backend" in e for e in errors)

    def test_invalid_caption_source_value(self):
        from src.config import validate_settings
        s = self._make_settings(caption_source="azure")
        errors = validate_settings(s)
        assert any("caption_source" in e for e in errors)

    def test_wasapi_on_linux_invalid(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.config import validate_settings
        s = self._make_settings(audio_backend="wasapi")
        errors = validate_settings(s)
        assert any("wasapi" in e.lower() and "windows" in e.lower() for e in errors)

    def test_pipewire_on_windows_invalid(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.config import validate_settings
        s = self._make_settings(audio_backend="pipewire")
        errors = validate_settings(s)
        assert any("pipewire" in e.lower() and "windows" in e.lower() for e in errors)

    def test_windows_live_captions_on_linux_invalid(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.config import validate_settings
        s = self._make_settings(caption_source="windows_live_captions")
        errors = validate_settings(s)
        assert any("windows_live_captions" in e for e in errors)

    def test_negative_sample_rate(self):
        from src.config import validate_settings
        s = self._make_settings(sample_rate=-1)
        errors = validate_settings(s)
        assert any("sample_rate" in e for e in errors)

    def test_invalid_channels(self):
        from src.config import validate_settings
        s = self._make_settings(channels=3)
        errors = validate_settings(s)
        assert any("channels" in e for e in errors)

    def test_assert_settings_valid_raises(self):
        from src.config import assert_settings_valid, ConfigValidationError
        s = self._make_settings(audio_backend="invalid")
        with pytest.raises(ConfigValidationError):
            assert_settings_valid(s)

    def test_assert_settings_valid_passes(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.config import assert_settings_valid
        # Não deve lançar
        assert_settings_valid(self._make_settings())


class TestAutoFallbackLinux:
    """Critério de aceite: 'auto' fallback para 'local_stt' em Linux."""

    def test_auto_resolves_to_local_stt_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: True)
        from src.platform.selector import select_caption_source
        assert select_caption_source("auto") == "local_stt"

    def test_auto_resolves_to_windows_live_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.platform.selector import select_caption_source
        assert select_caption_source("auto") == "windows_live_captions"


class TestChunkFormatCompatibility:
    """Critério de aceite: chunks de áudio compatíveis com pipeline existente."""

    def test_audio_chunk_default_format(self):
        from src.platform.types import AudioChunk
        chunk = AudioChunk(data=b"\x00\x01")
        # Formato esperado pelo pipeline: 16kHz, mono, PCM s16le
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1

    def test_audio_capture_config_defaults(self):
        from src.platform.types import AudioCaptureConfig
        cfg = AudioCaptureConfig()
        assert cfg.sample_rate == 16000
        assert cfg.channels == 1
        assert cfg.format == "pcm_s16le"
        assert cfg.chunk_frames == 480  # 30ms @ 16kHz

    def test_audio_device_dataclass(self):
        from src.platform.types import AudioDevice
        d = AudioDevice(id="42", name="Test", kind="input", channels=1, sample_rate=16000)
        assert d.id == "42"
        assert d.kind == "input"
        assert d.backend == ""  # default
