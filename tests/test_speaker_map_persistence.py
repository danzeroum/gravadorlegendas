"""Testes headless para carregamento do speaker map persistido.

Garante que o caminho de inicialização entrega o mapping persistido ao
ResultsPanel sem exigir display real.
"""
from __future__ import annotations

from src.ui.app import apply_speaker_map


class _FakeResultsPanel:
    def __init__(self):
        self.loaded: dict | None = None
        self.load_calls = 0

    def load_speaker_map(self, mapping: dict):
        self.loaded = mapping
        self.load_calls += 1


class _NoOpPanel:
    """Painel sem load_speaker_map — helper deve ignorar silenciosamente."""
    pass


class TestApplySpeakerMap:
    def test_delivers_persisted_mapping(self):
        panel = _FakeResultsPanel()
        mapping = {
            "speaker_0": {"name": "Alice", "color": "#3498db"},
            "speaker_1": {"name": "Bob", "color": "#e74c3c"},
        }
        apply_speaker_map(panel, mapping)
        assert panel.loaded == mapping
        assert panel.load_calls == 1

    def test_empty_mapping_does_nothing(self):
        panel = _FakeResultsPanel()
        apply_speaker_map(panel, {})
        assert panel.loaded is None
        assert panel.load_calls == 0

    def test_panel_without_method_is_safe(self):
        panel = _NoOpPanel()
        mapping = {"speaker_0": {"name": "Alice"}}
        apply_speaker_map(panel, mapping)
        # Não deve levantar
        assert not hasattr(panel, "loaded")
