"""IMP-06 — importação em segundo plano: progresso, resultado, cancelamento."""
import queue
import threading
import time

import pytest

from src.audio import file_pipeline as fp
from src.audio.file_pipeline import FileTranscript
from src.audio.models import CaptionSegment
from src.ui.view_models.import_job import ImportJob


def _thread_job(path="a.mp3", options=None):
    return ImportJob(
        path, options,
        process_factory=lambda target, args: threading.Thread(
            target=target, args=args, daemon=True),
        queue_factory=queue.Queue,
        event_factory=threading.Event,
    )


def _wait_done(job, timeout=5.0):
    events = []
    deadline = time.monotonic() + timeout
    while not job.done and time.monotonic() < deadline:
        events.extend(job.poll())
        time.sleep(0.01)
    return events


def _fake_transcribe(monkeypatch, *, block=None, error=None):
    def fake(path, *, on_progress, cancel, **options):
        on_progress(0.5, "Transcrevendo…")
        if block is not None:
            while not cancel.is_set():
                time.sleep(0.01)
            raise fp.TranscriptionCancelled()
        if error:
            raise error
        on_progress(1.0, "Concluído")
        return FileTranscript(
            source=path, duration_s=3.0, diarized=True,
            segments=[CaptionSegment(0.0, 1.0, "Bom dia", "SPEAKER_00")],
            speakers={"SPEAKER_00": "Participante A"},
        )
    monkeypatch.setattr(fp, "transcribe_audio_file", fake)


def test_result_roundtrip_and_progress(monkeypatch):
    _fake_transcribe(monkeypatch)
    job = _thread_job(options={"num_speakers": 2})
    job.start()
    events = _wait_done(job)
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "result" and "progress" in kinds
    tr = events[-1]["transcript"]
    assert tr.speakers == {"SPEAKER_00": "Participante A"}
    assert (tr.segments[0].text, tr.segments[0].speaker) == ("Bom dia", "SPEAKER_00")
    assert job.progress == 1.0


def test_cancel_is_cooperative(monkeypatch):
    _fake_transcribe(monkeypatch, block=True)
    job = _thread_job()
    job.start()
    time.sleep(0.05)
    job.cancel()
    assert job.cancel_requested
    assert _wait_done(job)[-1]["type"] == "cancelled"


def test_error_message_is_forwarded(monkeypatch):
    _fake_transcribe(monkeypatch, error=ValueError("arquivo sem faixa de áudio"))
    job = _thread_job()
    job.start()
    assert _wait_done(job)[-1] == {"type": "error", "message": "arquivo sem faixa de áudio"}


def test_dead_process_without_final_event_is_an_error():
    class Dead:
        def start(self):
            pass

        def is_alive(self):
            return False

    job = ImportJob("x", process_factory=lambda target, args: Dead(),
                    queue_factory=queue.Queue, event_factory=threading.Event)
    job.start()
    events = job.poll()
    assert job.done and events[-1]["type"] == "error"


def test_real_spawn_process_reports_decode_error(tmp_path):
    """Processo spawn de verdade (sem modelo): arquivo corrompido → erro."""
    pytest.importorskip("av")
    bad = tmp_path / "corrompido.mp3"
    bad.write_bytes(b"nao e audio" * 50)
    job = ImportJob(str(bad))
    job.start()
    events = _wait_done(job, timeout=60)
    assert events and events[-1]["type"] == "error"
    assert "corrompido.mp3" in events[-1]["message"]


# --- arquivos de saída ------------------------------------------------------

def test_output_base_never_overwrites(tmp_path):
    assert fp.output_base_for("/x/audio_celular.m4a", tmp_path) == tmp_path / "audio_celular"
    (tmp_path / "audio_celular.srt").write_text("x")
    assert fp.output_base_for("audio_celular.m4a", tmp_path) == tmp_path / "audio_celular_2"


def test_write_transcript_files_uses_names(tmp_path):
    tr = FileTranscript(source="a.mp3", duration_s=2.0, diarized=True,
                        segments=[CaptionSegment(0.0, 1.0, "Oi", "SPEAKER_00"),
                                  CaptionSegment(1.0, 2.0, "Olá", "SPEAKER_01")],
                        speakers={"SPEAKER_00": "Participante A", "SPEAKER_01": "Participante B"})
    written = fp.write_transcript_files(tr, tmp_path / "a", {"SPEAKER_01": "Juliana"})
    assert [p.suffix for p in written] == [".txt", ".srt", ".vtt"]
    txt = (tmp_path / "a.txt").read_text(encoding="utf-8")
    assert txt == "[00:00:00] Participante A: Oi\n[00:00:01] Juliana: Olá\n"
