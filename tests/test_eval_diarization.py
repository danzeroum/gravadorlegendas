"""AVL-04 — avaliador de diarização e comparação antes/depois (Frente H1)."""
import json
from argparse import Namespace
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from scripts import eval_diarization as ev  # noqa: E402
from src.audio.rttm import format_rttm, parse_rttm  # noqa: E402

CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


def _report(pipeline, **agg):
    return {"pipeline": pipeline, "aggregate": {"items_ok": 1, "items_error": 0, **agg}}


def test_compare_flags_regression_in_lower_is_better():
    table, regressed = ev.compare(_report("a", der=0.20), _report("b", der=0.25))
    assert regressed and "PIOROU" in table


def test_compare_accepts_improvement_and_noise_within_limit():
    _, regressed = ev.compare(_report("a", der=0.20, cp_wer=0.3),
                              _report("b", der=0.205, cp_wer=0.2))
    assert not regressed


def test_compare_coverage_is_higher_is_better():
    _, regressed = ev.compare(_report("a", coverage=0.95), _report("b", coverage=0.80))
    assert regressed


def test_cli_compare_exit_code(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_report("a", der=0.1)))
    b.write_text(json.dumps(_report("b", der=0.3)))
    assert ev.main(["--compare", str(a), str(b)]) == 1
    assert ev.main(["--compare", str(b), str(a)]) == 0


def test_load_synthetic_corpus_only_items_with_rttm():
    name, items = ev.load_corpus(CORPUS)
    ids = {i["id"] for i in items}
    assert ids == {"two_speakers_no_overlap", "two_speakers_overlap",
                   "three_speakers", "speaker_enter_exit"}
    assert all(i["audio"].is_file() and i["rttm"].is_file() for i in items)


def test_read_transcript(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("A\tbom dia\nB\toi\nA\ttudo bem\nlinha sem tab\n", encoding="utf-8")
    assert ev.read_transcript(p) == {"A": "bom dia tudo bem", "B": "oi"}


# --- DER real: pyannote.metrics -------------------------------------------

def _need_metrics():
    pytest.importorskip("pyannote.metrics",
                        reason="extra .[diarization-metrics] ausente")


def test_oracle_pipeline_has_zero_der_and_no_text_in_report():
    _need_metrics()
    report = ev.run(CORPUS, "oracle", Namespace())
    assert report["aggregate"]["der"] == 0.0
    assert report["aggregate"]["items_ok"] == 4
    assert "_components" not in report["items"][0]
    dumped = json.dumps(report)
    assert str(CORPUS) not in dumped  # sem caminhos locais


def test_rttm_pipeline_detects_shift(tmp_path):
    _need_metrics()
    for item in ev.load_corpus(CORPUS)[1]:
        ref = parse_rttm(item["rttm"])
        shifted = [dict(s, start=s["start"] + 0.5, end=s["end"] + 0.5) for s in ref]
        (tmp_path / f"{item['id']}.rttm").write_text(format_rttm(shifted, item["id"]))
    report = ev.run(CORPUS, "rttm", Namespace(hyp_dir=tmp_path))
    assert 0.1 < report["aggregate"]["der"] < 0.8


def test_failing_item_is_recorded_not_fatal(tmp_path):
    _need_metrics()
    report = ev.run(CORPUS, "rttm", Namespace(hyp_dir=tmp_path))  # vazio
    assert report["aggregate"]["items_ok"] == 0
    assert all(r["status"] == "error" for r in report["items"])
    assert "FileNotFoundError" in report["items"][0]["error"]


def test_words_produce_coverage_and_cp_wer(tmp_path):
    _need_metrics()
    transcript = tmp_path / "t.txt"
    transcript.write_text("S0\tbom dia\nS1\toi tudo bem\n", encoding="utf-8")
    rttm = tmp_path / "r.rttm"
    rttm.write_text(format_rttm([
        {"speaker": "S0", "start": 0.0, "end": 1.0},
        {"speaker": "S1", "start": 1.0, "end": 2.0},
    ], "r"))
    item = {"id": "r", "rttm": rttm, "transcript": transcript}
    words = [{"text": "bom", "speaker": "B"}, {"text": "dia", "speaker": "B"},
             {"text": "oi", "speaker": "A"}, {"text": "tudo", "speaker": "A"},
             {"text": "bem", "speaker": None}]
    row = ev.evaluate_item(item, {"turns": parse_rttm(rttm), "words": words})
    assert row["coverage"] == 0.8
    assert row["cp_wer"] == pytest.approx(1 / 5)
