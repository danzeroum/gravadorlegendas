"""ALN-05, IMP-02, IMP-04 — pipeline de arquivo com falante por palavra."""
import json
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("av", reason="PyAV ausente (decodificação do arquivo)")

from scripts import transcribe_file as tf  # noqa: E402
from src.audio import file_pipeline as fp  # noqa: E402
from src.audio.offline_diarizer import DiarizationUnavailable, SpeakerTurn  # noqa: E402
from tests.media_fixtures import write_tone  # noqa: E402


def _w(a, b, t):
    return SimpleNamespace(start=a, end=b, word=f" {t}")


class FakeWhisper:
    def __init__(self):
        self.kwargs = None
        self.path = None

    def transcribe(self, path, **kwargs):
        self.path, self.kwargs = path, kwargs
        segs = [
            SimpleNamespace(start=0.1, end=1.0, text=" Bom dia.",
                            words=[_w(0.1, 0.4, "Bom"), _w(0.5, 1.0, "dia.")]),
            SimpleNamespace(start=1.2, end=1.9, text=" Oi, tudo?",
                            words=[_w(1.2, 1.5, "Oi,"), _w(1.6, 1.9, "tudo?")]),
        ]
        if not kwargs.get("word_timestamps"):
            for s in segs:
                s.words = None
        return iter(segs), None


class FakeDiarizer:
    def __init__(self, ready=True, fail=False):
        self.ready, self.fail, self.calls = ready, fail, []

    def check_ready(self):
        if not self.ready:
            raise DiarizationUnavailable("sem token: defina HF_TOKEN")

    def diarize(self, wav, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("modelo quebrou")
        return [SpeakerTurn("SPEAKER_00", 0.0, 1.1), SpeakerTurn("SPEAKER_01", 1.1, 2.0)]


@pytest.fixture
def audio(tmp_path):
    return write_tone(tmp_path / "celular.m4a", "aac", duration_s=2.0)


def test_mp4_like_input_is_decoded_and_split_by_speaker(audio):
    model, diar = FakeWhisper(), FakeDiarizer()
    res = fp.transcribe_audio_file(audio, model=model, diarizer=diar, num_speakers=2)
    assert res.diarized and res.diarization_error is None
    assert [(s.speaker, s.text) for s in res.segments] == [
        ("SPEAKER_00", "Bom dia."), ("SPEAKER_01", "Oi, tudo?"),
    ]
    assert model.kwargs["word_timestamps"] is True
    assert model.path.endswith(".wav")  # Whisper e diarizador leem o mesmo WAV
    assert diar.calls[0]["num_speakers"] == 2
    assert res.duration_s == pytest.approx(2.0, abs=0.06)


def test_temp_wav_is_removed(audio):
    model = FakeWhisper()
    fp.transcribe_audio_file(audio, model=model, diarizer=FakeDiarizer())
    from pathlib import Path
    assert not Path(model.path).exists()


def test_without_diarization_still_transcribes_and_explains(audio):
    res = fp.transcribe_audio_file(audio, model=FakeWhisper(),
                                   diarizer=FakeDiarizer(ready=False))
    assert not res.diarized
    assert "HF_TOKEN" in res.diarization_error
    assert [s.text for s in res.segments] == ["Bom dia.", "Oi, tudo?"]
    assert all(s.speaker is None for s in res.segments)


def test_diarization_failure_keeps_transcript(audio):
    res = fp.transcribe_audio_file(audio, model=FakeWhisper(),
                                   diarizer=FakeDiarizer(fail=True))
    assert not res.diarized and "modelo quebrou" in res.diarization_error
    assert len(res.segments) == 2


def test_require_diarization_raises(audio):
    with pytest.raises(DiarizationUnavailable):
        fp.transcribe_audio_file(audio, model=FakeWhisper(),
                                 diarizer=FakeDiarizer(ready=False),
                                 require_diarization=True)


def test_progress_is_monotonic_and_ends_at_one(audio):
    seen = []
    fp.transcribe_audio_file(audio, model=FakeWhisper(), diarizer=FakeDiarizer(),
                             on_progress=lambda f, stage: seen.append((f, stage)))
    fractions = [f for f, _ in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert any("Separando vozes" in st for _, st in seen)


def test_cancel_interrupts(audio):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(fp.TranscriptionCancelled):
        fp.transcribe_audio_file(audio, model=FakeWhisper(), diarizer=FakeDiarizer(),
                                 cancel=cancel)


# --- CLI --------------------------------------------------------------------

def test_cli_diarize_writes_speaker_labels_with_names(audio, tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "load_model", lambda *a: FakeWhisper())
    diar = FakeDiarizer()
    monkeypatch.setattr("src.audio.offline_diarizer.OfflineDiarizer", lambda: diar)
    names = tmp_path / "nomes.json"
    names.write_text(json.dumps({"SPEAKER_00": {"name": "Juliana", "color": "#f00"}}))
    assert tf.main([str(audio), "--diarize", "--speaker-map", str(names)]) == 0
    srt = audio.with_suffix(".srt").read_text(encoding="utf-8")
    assert "[Juliana] Bom dia." in srt and "[SPEAKER_01] Oi, tudo?" in srt
    txt = audio.with_suffix(".txt").read_text(encoding="utf-8")
    assert "Juliana: Bom dia." in txt


def test_cli_diarize_fails_fast_without_token(audio, monkeypatch, capsys):
    def _no_model(*a):
        raise AssertionError("Whisper não deveria carregar")
    monkeypatch.setattr(tf, "load_model", _no_model)
    monkeypatch.setattr("src.audio.offline_diarizer.OfflineDiarizer",
                        lambda: FakeDiarizer(ready=False))
    assert tf.main([str(audio), "--diarize"]) == 2
    assert "HF_TOKEN" in capsys.readouterr().err


def test_speaker_map_accepts_plain_names(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"SPEAKER_00": "Ana"}))
    assert tf.load_speaker_map(str(p)) == {"SPEAKER_00": "Ana"}
