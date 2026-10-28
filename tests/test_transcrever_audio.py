"""Ponto de entrada do agente (opencode): scripts/transcrever_audio.py."""
import json

import pytest

from scripts import transcrever_audio as ta
from src.audio.file_pipeline import FileTranscript
from src.audio.models import CaptionSegment


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    audios = tmp_path / "audios"
    audios.mkdir()
    out = audios / "transcricoes"
    monkeypatch.setattr(ta, "ROOT", tmp_path)
    monkeypatch.setattr(ta, "AUDIO_DIR", audios)
    monkeypatch.setattr(ta, "OUTPUT_DIR", out)
    monkeypatch.setattr(ta, "SEARCH_DIRS", (audios, tmp_path))
    for name in ("Reunião Segunda.m4a", "reuniao_terca.mp3", "entrevista.MP4", "notas.txt"):
        (audios / name).write_bytes(b"x")
    return audios, out


def test_find_exact_ignoring_case_and_accents(dirs):
    audios, _ = dirs
    assert ta.find_audio("reuniao segunda") == audios / "Reunião Segunda.m4a"
    assert ta.find_audio("ENTREVISTA") == audios / "entrevista.MP4"
    assert ta.find_audio("reuniao_terca.mp3") == audios / "reuniao_terca.mp3"


def test_find_partial_and_direct_path(dirs, tmp_path):
    audios, _ = dirs
    assert ta.find_audio("terca") == audios / "reuniao_terca.mp3"
    other = tmp_path / "fora.wav"
    other.write_bytes(b"x")
    assert ta.find_audio(str(other)) == other


def test_ambiguous_lists_options(dirs):
    with pytest.raises(ta.UserError) as exc:
        ta.find_audio("reuniao")
    assert exc.value.code == ta.EXIT_AMBIGUOUS
    assert "reuniao_terca.mp3" in str(exc.value) and "Segunda" in str(exc.value)


def test_not_found_lists_available_and_ignores_non_audio(dirs):
    with pytest.raises(ta.UserError) as exc:
        ta.find_audio("notas")
    assert exc.value.code == ta.EXIT_NOT_FOUND
    assert "entrevista.MP4" in str(exc.value) and "notas.txt" not in str(exc.value)


SPEAKERS = {"SPEAKER_00": "Participante A", "SPEAKER_01": "Participante B"}


@pytest.mark.parametrize("pair,sid", [
    ("A=Juliana", "SPEAKER_00"), ("participante b=Juliana", "SPEAKER_01"),
    ("SPEAKER_01=Juliana", "SPEAKER_01"),
])
def test_parse_names(pair, sid):
    assert ta.parse_names([pair], SPEAKERS) == {sid: "Juliana"}


def test_parse_names_unknown_participant():
    with pytest.raises(ta.UserError, match="Participante 'C' não existe"):
        ta.parse_names(["C=Ana"], SPEAKERS)


def _fake_pipeline(monkeypatch, diarized=True, error=None):
    calls = {}

    def fake(path, **kwargs):
        calls.update(kwargs, path=path)
        kwargs["on_progress"](1.0, "Concluído")
        return FileTranscript(
            source=str(path), duration_s=65.0, diarized=diarized, diarization_error=error,
            segments=[CaptionSegment(0.0, 2.0, "Bom dia.", "SPEAKER_00" if diarized else None),
                      CaptionSegment(61.0, 63.0, "Oi!", "SPEAKER_01" if diarized else None)],
            speakers=dict(SPEAKERS) if diarized else {},
        )
    monkeypatch.setattr("src.audio.file_pipeline.transcribe_audio_file", fake)
    monkeypatch.setattr(ta, "environment_report",
                        lambda: {"faster_whisper": True, "av": True})
    return calls


def test_transcribe_writes_all_files_and_result_block(dirs, monkeypatch, capsys):
    _, out = dirs
    calls = _fake_pipeline(monkeypatch)
    assert ta.main(["segunda", "--participantes", "2", "--modelo", "small"]) == 0
    assert calls["num_speakers"] == 2 and calls["model_size"] == "small"
    assert calls["diarize"] is True
    stem = "Reunião Segunda"
    for ext in (".txt", ".srt", ".vtt", ".md", ".json"):
        assert (out / stem).with_suffix(ext).exists(), ext
    md = (out / stem).with_suffix(".md").read_text(encoding="utf-8")
    assert "**Participante A** `[00:00:00]` Bom dia." in md
    assert "Participantes:** Participante A, Participante B" in md
    printed = capsys.readouterr().out
    assert "=== RESULTADO ===" in printed and "participantes: 2" in printed
    data = json.loads((out / stem).with_suffix(".json").read_text(encoding="utf-8"))
    assert data["source"] == "audios/Reunião Segunda.m4a"  # sem caminho absoluto


def test_existing_transcript_is_reused(dirs, monkeypatch, capsys):
    calls = _fake_pipeline(monkeypatch)
    ta.main(["terca"])
    calls.clear()
    assert ta.main(["terca"]) == 0
    assert calls == {}  # não retranscreveu
    assert "já existia" in capsys.readouterr().out


def test_rename_rewrites_without_retranscribing(dirs, monkeypatch):
    _, out = dirs
    calls = _fake_pipeline(monkeypatch)
    ta.main(["terca"])
    calls.clear()
    assert ta.main(["--renomear", "terca", "A=Juliana", "B=Daniel"]) == 0
    assert calls == {}
    assert "[Juliana] Bom dia." in (out / "reuniao_terca.srt").read_text(encoding="utf-8")
    assert "Daniel: Oi!" in (out / "reuniao_terca.txt").read_text(encoding="utf-8")
    # Renomear de novo acumula os nomes.
    ta.main(["--renomear", "terca", "B=Ana"])
    txt = (out / "reuniao_terca.txt").read_text(encoding="utf-8")
    assert "Juliana: Bom dia." in txt and "Ana: Oi!" in txt


def test_without_diarization_warns_and_rename_is_refused(dirs, monkeypatch, capsys):
    _fake_pipeline(monkeypatch, diarized=False, error="token do Hugging Face ausente")
    assert ta.main(["entrevista"]) == 0
    out = capsys.readouterr().out
    assert "Participantes não separados: token" in out
    assert "participantes: não separados" in out
    assert ta.main(["--renomear", "entrevista", "A=X"]) == ta.EXIT_NO_TRANSCRIPT


def test_missing_dependencies_exit_2(dirs, monkeypatch):
    monkeypatch.setattr(ta, "environment_report",
                        lambda: {"faster_whisper": False, "av": True})
    assert ta.main(["terca"]) == ta.EXIT_ENV


def test_list_marks_transcribed(dirs, monkeypatch, capsys):
    _fake_pipeline(monkeypatch)
    ta.main(["terca"])
    capsys.readouterr()
    assert ta.main(["--listar"]) == 0
    out = capsys.readouterr().out
    assert "reuniao_terca.mp3  (já transcrito)" in out and "entrevista.MP4" in out


def test_verificar_never_prints_token(monkeypatch, capsys):
    monkeypatch.setenv("HF_TOKEN", "hf_SEGREDO_DE_TESTE_123")
    rc = ta.main(["--verificar"])
    out = capsys.readouterr().out
    assert "hf_SEGREDO" not in out
    assert "token Hugging Face" in out
    assert rc in (0, ta.EXIT_ENV)
