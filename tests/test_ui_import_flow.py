"""IMP-05, IMP-07 — fluxo de importação na janela (headless, com fakes).

Chama os métodos de ``MainWindow`` sobre um objeto falso, sem instanciar
CustomTkinter (mesmo estilo de tests/test_main_window_shutdown.py).
"""
from __future__ import annotations

import pytest

pytest.importorskip("customtkinter")

from src.audio.file_pipeline import FileTranscript  # noqa: E402
from src.audio.models import CaptionSegment  # noqa: E402
from src.config import settings  # noqa: E402
from src.ui import app as app_mod  # noqa: E402
from src.ui.app import MainWindow, _shutdown  # noqa: E402
from src.ui.view_models.import_job import (  # noqa: E402
    format_transcript_lines, parse_participants, progress_text,
)
from src.ui.view_models.recording_state import RecordingState, RecordingStateMachine  # noqa: E402


class Recorder:
    """Registra qualquer chamada: obj.metodo(args) → calls."""

    def __init__(self, **returns):
        self.calls = []
        self._returns = returns

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self._returns.get(name)
        return method

    def names(self):
        return [c[0] for c in self.calls]


class FakeResults(Recorder):
    def __init__(self):
        super().__init__()
        self.map = {}

    def load_speaker_map(self, mapping):
        self.calls.append(("load_speaker_map", (mapping,), {}))
        self.map = dict(mapping)

    def get_speaker_map(self):
        return {k: v for k, v in self.map.items() if v.get("name")}

    def get_speaker_display_name(self, sid):
        if not sid or sid not in self.map:
            return ""
        return f"● {self.map[sid]['name'] or sid}: "


class FakeTranscription(Recorder):
    def __init__(self):
        super().__init__()
        self.lines = []

    def clear(self):
        self.lines = []

    def append_line(self, line):
        self.lines.append(line)


class FakeJob:
    def __init__(self, events, done=True):
        self._events, self.done = events, done
        self.cancelled = self.terminated = False

    def poll(self):
        ev, self._events = self._events, []
        return ev

    def cancel(self):
        self.cancelled = True

    def terminate(self):
        self.terminated = True


def make_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "recording_dir", str(tmp_path))
    w = MainWindow.__new__(MainWindow)
    w._machine = RecordingStateMachine()
    w._controls = Recorder()
    w._header = Recorder()
    w._toast = Recorder()
    w._statusbar = Recorder()
    w._root = Recorder()
    w._results = FakeResults()
    w._transcription = FakeTranscription()
    w._audio_transcript_lines = []
    w._import_job = None
    w._last_import = None
    w._last_import_base = None
    w._save_speaker_map = lambda: None
    w._session_feed_audio_line = lambda line: None
    return w


def transcript(diarized=True, error=None):
    segs = [CaptionSegment(0.0, 1.5, "Bom dia.", "SPEAKER_00" if diarized else None),
            CaptionSegment(62.0, 63.0, "Oi, tudo?", "SPEAKER_01" if diarized else None)]
    return FileTranscript(
        source="/celular/audio_celular.m4a", duration_s=63.0, segments=segs,
        diarized=diarized, diarization_error=error,
        speakers={"SPEAKER_00": "Participante A", "SPEAKER_01": "Participante B"} if diarized else {},
    )


def test_result_populates_panel_speakers_and_files(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([{"type": "progress", "progress": 0.5, "stage": "Transcrevendo…"},
                             {"type": "result", "transcript": transcript()}])
    w._poll_import()
    assert w._transcription.lines == [
        "[00:00:00] ● Participante A: Bom dia.",
        "[00:01:02] ● Participante B: Oi, tudo?",
    ]
    assert w._audio_transcript_lines == w._transcription.lines
    assert ("open", ("Falantes",), {}) in w._results.calls
    srt = (tmp_path / "audio_celular.srt").read_text(encoding="utf-8")
    assert "[Participante A] Bom dia." in srt
    # Encerrado: botão volta ao normal e gravação liberada.
    assert w._import_job is None
    assert ("set_importing", (False,), {}) in w._controls.calls
    assert ("set_timer", ("50%",), {}) in w._controls.calls


def test_rename_then_export_rewrites_files(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([{"type": "result", "transcript": transcript()}])
    w._poll_import()
    w._results.map["SPEAKER_00"]["name"] = "Juliana"
    w._refresh_import_outputs()
    assert w._transcription.lines[0] == "[00:00:00] ● Juliana: Bom dia."
    assert "Juliana: Bom dia." in (tmp_path / "audio_celular.txt").read_text(encoding="utf-8")


def test_without_diarization_warns_with_reason(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([{"type": "result",
                              "transcript": transcript(False, "token do Hugging Face ausente")}])
    w._poll_import()
    assert w._transcription.lines[0] == "[00:00:00] Bom dia."
    toast = [c for c in w._toast.calls if c[0] == "show"][-1]
    assert "sem separar participantes" in toast[1][0] and toast[2]["kind"] == "warn"
    assert "load_speaker_map" not in w._results.names()


def test_running_job_keeps_polling(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([], done=False)
    w._poll_import()
    assert w._root.names() == ["after"]


def test_error_event_shows_message(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([{"type": "error", "message": "'x.mp3' não tem faixa de áudio."}])
    w._poll_import()
    assert ("set_error", ("Erro: 'x.mp3' não tem faixa de áudio.",), {}) in w._controls.calls


def test_click_while_importing_cancels(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    job = FakeJob([], done=False)
    w._import_job = job
    w._on_import_clicked()
    assert job.cancelled


def test_import_blocked_while_recording(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._machine.transition(RecordingState.STARTING)
    monkeypatch.setattr(app_mod.tkfiledialog, "askopenfilename",
                        lambda **k: pytest.fail("não deveria abrir o seletor"))
    w._on_import_clicked()
    assert "Pare a gravação" in w._toast.calls[-1][1][0]


def test_ctrl_r_blocked_while_importing(tmp_path, monkeypatch):
    w = make_window(tmp_path, monkeypatch)
    w._import_job = FakeJob([], done=False)
    w._start_recording = lambda: pytest.fail("não pode gravar durante importação")
    w._on_toggle_recording()
    assert "Aguarde a importação" in w._toast.calls[-1][1][0]


def test_shutdown_terminates_running_import():
    class Win:
        _import_job = FakeJob([], done=False)
        _audio_manager = type("A", (), {"is_running": False})()
        session = type("S", (), {"stop": lambda self: None})()
        _root = type("R", (), {"geometry": lambda self: "1x1"})()

    class Store:
        def set(self, k, v):
            pass

    win = Win()
    _shutdown(win, Store())
    assert win._import_job.terminated


# --- helpers puros ----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [("", None), ("  ", None), ("3", 3), (" 12 ", 12)])
def test_parse_participants(text, expected):
    assert parse_participants(text) == expected


@pytest.mark.parametrize("text", ["0", "21", "dois", "-1", "2.5"])
def test_parse_participants_invalid(text):
    with pytest.raises(ValueError):
        parse_participants(text)


def test_format_lines_and_progress_text():
    lines = format_transcript_lines(transcript(), lambda sid: f"{sid}: " if sid else "")
    assert lines[1] == "[00:01:02] SPEAKER_01: Oi, tudo?"
    assert progress_text(0.354, "Transcrevendo…") == "Transcrevendo — 35%"
