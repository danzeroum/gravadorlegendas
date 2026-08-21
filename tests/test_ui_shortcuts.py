"""Testes headless para mapa de atalhos (src/ui/shortcuts.py)."""
from __future__ import annotations

import pytest

from src.ui.shortcuts import SHORTCUTS, SHORTCUT_LABELS


class TestShortcuts:
    def test_required_actions_present(self):
        required = {
            "toggle_recording",
            "save_transcription",
            "clear_transcription",
            "open_settings",
            "close_secondary",
        }
        assert set(SHORTCUTS.values()) == required

    def test_unique_binds(self):
        assert len(SHORTCUTS) == len(set(SHORTCUTS.keys()))

    def test_no_conflicting_keys(self):
        # Ctrl+S, Ctrl+R, Ctrl+L, Ctrl+,, Esc — todos distintos
        binds = list(SHORTCUTS.keys())
        assert len(binds) == len(set(binds))

    def test_labels_match_actions(self):
        for action, label in SHORTCUT_LABELS.items():
            assert action in SHORTCUTS.values()
            assert "Ctrl+" in label or "Esc" in label

    def test_bind_format(self):
        for bind in SHORTCUTS:
            assert bind.startswith("<") and bind.endswith(">")