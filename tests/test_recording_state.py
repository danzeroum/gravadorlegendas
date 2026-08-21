"""Testes headless para máquina de estado de gravação (src/ui/view_models/recording_state.py)."""
from __future__ import annotations

import pytest

from src.ui.view_models.recording_state import (
    RecordingState,
    RecordingStateMachine,
    format_duration,
    InvalidTransitionError,
)


class TestRecordingStateMachine:
    def test_initial_state(self):
        m = RecordingStateMachine()
        assert m.state == RecordingState.IDLE

    def test_allowed_transitions(self):
        m = RecordingStateMachine()
        assert m.can_transition(RecordingState.STARTING)
        assert not m.can_transition(RecordingState.RECORDING)

    def test_idle_to_starting(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        assert m.state == RecordingState.STARTING

    def test_starting_to_recording(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        m.transition(RecordingState.RECORDING)
        assert m.state == RecordingState.RECORDING

    def test_recording_to_stopping(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        m.transition(RecordingState.RECORDING)
        m.transition(RecordingState.STOPPING)
        assert m.state == RecordingState.STOPPING

    def test_stopping_to_idle(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        m.transition(RecordingState.RECORDING)
        m.transition(RecordingState.STOPPING)
        m.transition(RecordingState.IDLE)
        assert m.state == RecordingState.IDLE

    def test_invalid_transitions_raise(self):
        m = RecordingStateMachine()
        with pytest.raises(InvalidTransitionError):
            m.transition(RecordingState.RECORDING)  # IDLE -> RECORDING inválido
        m.transition(RecordingState.STARTING)
        with pytest.raises(InvalidTransitionError):
            m.transition(RecordingState.STOPPING)  # STARTING -> STOPPING inválido
        m.transition(RecordingState.RECORDING)
        with pytest.raises(InvalidTransitionError):
            m.transition(RecordingState.STARTING)  # RECORDING -> STARTING inválido

    def test_derived_properties_idle(self):
        m = RecordingStateMachine()
        assert m.primary_button_text == "▶ Iniciar transcrição"
        assert m.primary_button_enabled is True
        assert m.status_text == "● Pronto"
        assert m.status_kind == "idle"
        assert m.is_active is False

    def test_derived_properties_starting(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        assert m.primary_button_text == "Iniciando…"
        assert m.primary_button_enabled is False
        assert m.status_text == "● Iniciando…"
        assert m.status_kind == "busy"
        assert m.is_active is True

    def test_derived_properties_recording(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        m.transition(RecordingState.RECORDING)
        assert m.primary_button_text == "■ Parar transcrição"
        assert m.primary_button_enabled is True
        assert m.status_text == "● Gravando"
        assert m.status_kind == "recording"
        assert m.is_active is True

    def test_derived_properties_stopping(self):
        m = RecordingStateMachine()
        m.transition(RecordingState.STARTING)
        m.transition(RecordingState.RECORDING)
        m.transition(RecordingState.STOPPING)
        assert m.primary_button_text == "Parando…"
        assert m.primary_button_enabled is False
        assert m.status_text == "● Parando…"
        assert m.status_kind == "busy"
        assert m.is_active is True


class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "00:00:00"

    def test_seconds(self):
        assert format_duration(45) == "00:00:45"

    def test_minutes(self):
        assert format_duration(125) == "00:02:05"

    def test_hours(self):
        assert format_duration(3661) == "01:01:01"

    def test_negative_clamped(self):
        assert format_duration(-10) == "00:00:00"