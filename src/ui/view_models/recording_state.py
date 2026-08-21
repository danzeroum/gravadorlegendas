"""Máquina de estado da gravação — lógica pura de apresentação.

Sem imports de UI: testável em ambiente headless.
"""
from __future__ import annotations

from enum import Enum


class RecordingState(Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"


_ALLOWED_TRANSITIONS: dict[RecordingState, frozenset] = {
    RecordingState.IDLE: frozenset({RecordingState.STARTING}),
    RecordingState.STARTING: frozenset({RecordingState.RECORDING, RecordingState.IDLE}),
    RecordingState.RECORDING: frozenset({RecordingState.STOPPING}),
    RecordingState.STOPPING: frozenset({RecordingState.IDLE}),
}


class InvalidTransitionError(RuntimeError):
    """Tentativa de transição inválida entre estados de gravação."""


class RecordingStateMachine:
    """Máquina de estados para controlar o fluxo de gravação na UI."""

    def __init__(self) -> None:
        self._state = RecordingState.IDLE

    @property
    def state(self) -> RecordingState:
        return self._state

    def can_transition(self, target: RecordingState) -> bool:
        return target in _ALLOWED_TRANSITIONS.get(self._state, frozenset())

    def transition(self, target: RecordingState) -> RecordingState:
        if not self.can_transition(target):
            raise InvalidTransitionError(
                f"Transição inválida: {self._state.value} -> {target.value}"
            )
        self._state = target
        return self._state

    # Derivações de apresentação ----------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._state in (
            RecordingState.STARTING,
            RecordingState.RECORDING,
            RecordingState.STOPPING,
        )

    @property
    def primary_button_text(self) -> str:
        if self._state == RecordingState.IDLE:
            return "▶ Iniciar transcrição"
        if self._state == RecordingState.STARTING:
            return "Iniciando…"
        if self._state == RecordingState.RECORDING:
            return "■ Parar transcrição"
        return "Parando…"  # STOPPING

    @property
    def primary_button_enabled(self) -> bool:
        return self._state in (RecordingState.IDLE, RecordingState.RECORDING)

    @property
    def status_text(self) -> str:
        if self._state == RecordingState.IDLE:
            return "● Pronto"
        if self._state == RecordingState.STARTING:
            return "● Iniciando…"
        if self._state == RecordingState.RECORDING:
            return "● Gravando"
        return "● Parando…"  # STOPPING

    @property
    def status_kind(self) -> str:
        if self._state == RecordingState.RECORDING:
            return "recording"
        if self._state == RecordingState.STARTING:
            return "busy"
        if self._state == RecordingState.STOPPING:
            return "busy"
        return "idle"


def format_duration(seconds: float) -> str:
    """Formata segundos como ``HH:MM:SS``."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
