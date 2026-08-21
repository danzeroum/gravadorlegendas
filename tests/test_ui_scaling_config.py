"""Testes headless para persistência de escala UI no config_store."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.config_store import ConfigStore, _DEFAULTS


class TestUiScalingConfig:
    def test_default_ui_scaling(self):
        store = ConfigStore()
        assert store.get("ui_scaling") == 1.0

    def test_persist_ui_scaling(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            # Monkey-patch _CONFIG_FILE
            import src.config_store as cs
            orig = cs._CONFIG_FILE
            cs._CONFIG_FILE = config_path
            try:
                store = ConfigStore()
                store.set("ui_scaling", 1.25)
                assert store.get("ui_scaling") == 1.25
                # nova instância carrega do disco
                store2 = ConfigStore()
                assert store2.get("ui_scaling") == 1.25
            finally:
                cs._CONFIG_FILE = orig

    def test_ui_scaling_in_defaults(self):
        assert "ui_scaling" in _DEFAULTS
        assert _DEFAULTS["ui_scaling"] == 1.0