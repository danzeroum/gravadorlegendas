"""Testes headless para shutdown limpo da MainWindow.

Não instanciam CustomTkinter — apenas testam as funções de shutdown
extraídas de src/ui/app.py com objetos fake.
"""
from __future__ import annotations

import pytest

from src.ui.app import _shutdown, _perform_window_close


class _FakeAudioManager:
    def __init__(self, running: bool = True):
        self.is_running = running
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1
        self.is_running = False


class _FakeSession:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _FakeRoot:
    def __init__(self, geometry: str = "1100x720+100+50"):
        self._geometry = geometry
        self.destroy_calls = 0

    def geometry(self):
        return self._geometry

    def destroy(self):
        self.destroy_calls += 1


class _FakeStore:
    def __init__(self):
        self.data: dict = {}

    def set(self, key: str, value):
        self.data[key] = value


class _FakeWindow:
    def __init__(self, audio_running: bool = True):
        self._audio_manager = _FakeAudioManager(running=audio_running)
        self.session = _FakeSession()
        self._root = _FakeRoot()
        self._closing = False


class TestShutdown:
    def test_shutdown_stops_audio_when_running(self):
        win = _FakeWindow(audio_running=True)
        store = _FakeStore()
        _shutdown(win, store)
        assert win._audio_manager.stop_calls == 1
        assert win.session.stop_calls == 1
        assert store.data.get("window_geometry") == "1100x720+100+50"

    def test_shutdown_skips_audio_when_idle(self):
        win = _FakeWindow(audio_running=False)
        store = _FakeStore()
        _shutdown(win, store)
        assert win._audio_manager.stop_calls == 0
        assert win.session.stop_calls == 1
        assert store.data.get("window_geometry") == "1100x720+100+50"

    def test_shutdown_persists_geometry(self):
        win = _FakeWindow(audio_running=True)
        win._root._geometry = "900x600+10+20"
        store = _FakeStore()
        _shutdown(win, store)
        assert store.data.get("window_geometry") == "900x600+10+20"


class TestPerformWindowClose:
    def test_closes_and_runs_shutdown(self):
        win = _FakeWindow(audio_running=True)
        store = _FakeStore()
        result = _perform_window_close(win, store)
        assert result is True
        assert win._audio_manager.stop_calls == 1
        assert win.session.stop_calls == 1
        assert win._root.destroy_calls == 1
        assert win._closing is True

    def test_idempotent_second_call(self):
        win = _FakeWindow(audio_running=True)
        store = _FakeStore()
        _perform_window_close(win, store)
        # Segunda chamada não deve reexecutar shutdown nem destroy
        result = _perform_window_close(win, store)
        assert result is False
        assert win._audio_manager.stop_calls == 1
        assert win.session.stop_calls == 1
        assert win._root.destroy_calls == 1

    def test_destroy_called_even_if_shutdown_raises(self):
        class _BadAudioManager(_FakeAudioManager):
            def stop(self):
                raise RuntimeError("audio crash")

        win = _FakeWindow(audio_running=True)
        win._audio_manager = _BadAudioManager()
        store = _FakeStore()
        with pytest.raises(RuntimeError, match="audio crash"):
            _perform_window_close(win, store)
        assert win._root.destroy_calls == 1
        assert win._closing is True
