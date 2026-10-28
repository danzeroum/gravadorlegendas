"""PRIV-01..03 — guarda de privacidade por caminho (Frente E0)."""
import pytest

from scripts.secret_scan_changed_files import classify_path, main


@pytest.mark.parametrize("rel", [
    "tests/fixtures/corpus/audio/three_speakers.wav",
    "tests/fixtures/corpus/rttm/three_speakers.rttm",
    "src/audio/diarize.py",
    "docs/diarizacao/PLANO-IMPLEMENTACAO.md",
])
def test_allowed_paths(rel):
    assert classify_path(rel) is None


@pytest.mark.parametrize("rel", [
    "data/recordings/reuniao_mic.wav",
    "docs/exemplo.m4a",
    "audio_celular.MP3",
    "examples/video.mp4",
    "tests/fixtures/whatsapp.opus",
    # Prefixo parecido não libera: precisa estar DENTRO do diretório.
    "tests/fixtures/corpus/audio_extra/x.wav",
])
def test_audio_outside_corpus_blocked(rel):
    assert classify_path(rel) == "audio_fora_do_corpus"


@pytest.mark.parametrize("rel", [
    "corpus_real/rttm/reuniao.rttm",
    "tests/fixtures/reuniao.rttm",
])
def test_rttm_outside_corpus_blocked(rel):
    assert classify_path(rel) == "rttm_fora_do_corpus"


@pytest.mark.parametrize("rel", [
    "src/voiceprints.json",
    "data/VoicePrints.enc",
    "tests/fixtures/corpus/audio/voiceprint_sample.wav",
])
def test_voiceprint_blocked_anywhere(rel):
    assert classify_path(rel) == "voiceprint"


def test_windows_separator_normalized():
    assert classify_path("tests\\fixtures\\corpus\\audio\\a.wav") is None


def test_tracked_paths_repo_is_clean(capsys):
    """O próprio repositório não versiona áudio real (roda no CI)."""
    assert main(["--tracked-paths"]) == 0


def test_tracked_paths_reports_without_content(monkeypatch, capsys):
    monkeypatch.setattr(
        "scripts.secret_scan_changed_files.tracked_files",
        lambda: ["src/a.py", "gravacao.wav"],
    )
    assert main(["--tracked-paths"]) == 1
    out = capsys.readouterr().out
    assert "gravacao.wav" in out and "audio_fora_do_corpus" in out
