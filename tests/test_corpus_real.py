"""AVL-02..03 — corpus real fora do repo, com hash/consentimento/retenção."""
import wave
from datetime import date

import numpy as np
import pytest

pytest.importorskip("yaml")
pytest.importorskip("av", reason="PyAV ausente (decodificação do áudio)")

from scripts import corpus_real as cr  # noqa: E402
from src.audio.rttm import parse_rttm_text  # noqa: E402

RTTM = (
    "SPEAKER r 1 0.000 1.000 <NA> <NA> A <NA> <NA>\n"
    "SPEAKER r 1 1.200 0.800 <NA> <NA> B <NA> <NA>\n"
)


def _wav(path, seconds=2.0):
    x = (np.sin(np.arange(int(16000 * seconds)) / 10) * 8000).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(x.tobytes())
    return path


@pytest.fixture
def corpus(tmp_path):
    src = tmp_path / "entrada"
    src.mkdir()
    audio = _wav(src / "reuniao.wav")
    rttm = src / "reuniao.rttm"
    rttm.write_text(RTTM, encoding="utf-8")
    cdir = cr.cmd_init(tmp_path / "corpus", "teste")
    cr.cmd_add(cdir, audio, rttm, "TERMO-1", "2030-01-01")
    return cdir


def test_init_inside_repo_is_refused():
    with pytest.raises(cr.CorpusError, match="dentro do repositório"):
        cr.cmd_init(cr.ROOT / "corpus_real_teste", "x")
    assert not (cr.ROOT / "corpus_real_teste").exists()


def test_add_registers_hash_consent_and_speakers(corpus):
    data = cr.load_manifest(corpus)
    item = data["items"][0]
    assert data["contains_personal_audio"] is True
    assert item["num_speakers"] == 2
    assert item["consent_ref"] == "TERMO-1"
    assert len(item["sha256"]["audio"]) == 64
    assert cr.cmd_verify(corpus) == []


def test_add_requires_consent(corpus, tmp_path):
    audio = _wav(tmp_path / "outra.wav")
    rttm = tmp_path / "outra.rttm"
    rttm.write_text(RTTM, encoding="utf-8")
    with pytest.raises(cr.CorpusError, match="consent"):
        cr.cmd_add(corpus, audio, rttm, "  ", "2030-01-01")


def test_verify_detects_tampered_file(corpus):
    with open(corpus / "rttm" / "reuniao.rttm", "a", encoding="utf-8") as f:
        f.write("SPEAKER r 1 3.0 1.0 <NA> <NA> C <NA> <NA>\n")
    assert any("sha256 divergente (rttm)" in p for p in cr.cmd_verify(corpus))


def test_verify_detects_expired_retention(corpus):
    problems = cr.cmd_verify(corpus, today=date(2031, 1, 1))
    assert any("retenção vencida" in p for p in problems)


def test_purge_dry_run_keeps_then_purge_removes(corpus):
    later = date(2031, 1, 1)
    assert cr.cmd_purge(corpus, dry_run=True, today=later) == ["reuniao"]
    assert (corpus / "audio" / "reuniao.wav").exists()
    assert cr.cmd_purge(corpus, today=later) == ["reuniao"]
    assert not (corpus / "audio" / "reuniao.wav").exists()
    assert cr.load_manifest(corpus)["items"] == []


def test_labels_to_rttm_audacity_format():
    labels = "0.5\t2.25\tJuliana\n\\\t200\t3000\n\n3.0\t4.0\tDaniel Silva\n"
    segs = parse_rttm_text(cr.labels_to_rttm(labels, "r"))
    assert segs == [
        {"speaker": "Juliana", "start": 0.5, "end": 2.25},
        {"speaker": "Daniel_Silva", "start": 3.0, "end": 4.0},
    ]


def test_labels_to_rttm_rejects_bad_interval():
    with pytest.raises(cr.CorpusError, match="linha 1"):
        cr.labels_to_rttm("2.0\t1.0\tA\n", "r")


def test_cli_verify_exit_codes(corpus, capsys):
    assert cr.main(["verify", "--dir", str(corpus)]) == 0
    (corpus / "audio" / "reuniao.wav").unlink()
    assert cr.main(["verify", "--dir", str(corpus)]) == 1
    assert "arquivo ausente" in capsys.readouterr().out
