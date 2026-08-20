"""Classe base para fontes de legenda."""
from __future__ import annotations

import abc


class CaptionSourceError(RuntimeError):
    """Erro de inicialização ou execução de uma fonte de legenda."""


class CaptionSourceBase(abc.ABC):
    """Classe base abstrata para fontes de legenda.

    Subclasses devem implementar ``_start``, ``_stop`` e a propriedade
    ``is_running``. A classe base garante idempotência (start/stop
    chamados duas vezes não causam erro).
    """

    def __init__(self, name: str = ""):
        self._name = name or self.__class__.__name__
        self._running = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Inicia a fonte de legenda (idempotente)."""
        if self._running:
            return
        self._start()
        self._running = True

    def stop(self) -> None:
        """Para a fonte de legenda (idempotente)."""
        if not self._running:
            return
        try:
            self._stop()
        finally:
            self._running = False

    @abc.abstractmethod
    def _start(self) -> None: ...

    @abc.abstractmethod
    def _stop(self) -> None: ...
