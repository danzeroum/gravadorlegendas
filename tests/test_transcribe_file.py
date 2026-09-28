"""Testes do script de transcrição offline (scripts/transcribe_file.py)."""
from types import SimpleNamespace

from scripts import transcribe_file as tf


class _FakeModel:
    def transcribe(self, path, **kwargs):
        segs = [
            SimpleNamespace(start=0.0, end=1.5, text=" Bom dia a todos. "),
            SimpleNamespace(start=1.5, end=1.5, text="inválido"),
            SimpleNamespace(start=2.0, end=3.0, text="   "),
            SimpleNamespace(start=3.0, end=5.25, text="Próximos passos."),
        ]
        return iter(segs), None


def test_transcribe_filters_empty_and_invalid_segments(tmp_path):
    segs = tf.transcribe(_FakeModel(), tmp_path / "a.wav",
                         language="pt", beam_size=1, vad_filter=True)
    assert [(s.start, s.end, s.text) for s in segs] == [
        (0.0, 1.5, "Bom dia a todos."),
        (3.0, 5.25, "Próximos passos."),
    ]


def test_write_outputs_creates_files_next_to_audio(tmp_path):
    audio = tmp_path / "reuniao_mic.wav"
    audio.write_bytes(b"")
    segs = tf.transcribe(_FakeModel(), audio,
                         language="pt", beam_size=1, vad_filter=True)
    written = tf.write_outputs(segs, audio, {"txt", "srt", "vtt"})
    assert {p.name for p in written} == {
        "reuniao_mic.txt", "reuniao_mic.srt", "reuniao_mic.vtt",
    }
    srt = (tmp_path / "reuniao_mic.srt").read_text(encoding="utf-8")
    assert "00:00:03,000 --> 00:00:05,250" in srt
    assert "Próximos passos." in srt
    assert (tmp_path / "reuniao_mic.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert "[00:00:00] Bom dia a todos." in (tmp_path / "reuniao_mic.txt").read_text(encoding="utf-8")


def test_main_skips_audio_that_already_has_subtitles(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.wav").write_bytes(b"")
    (tmp_path / "a.srt").write_text("x", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("x", encoding="utf-8")

    def _fail(*a, **k):
        raise AssertionError("modelo não deveria ser carregado")

    monkeypatch.setattr(tf, "load_model", _fail)
    assert tf.main([str(tmp_path)]) == 0
    assert "pulando" in capsys.readouterr().out
