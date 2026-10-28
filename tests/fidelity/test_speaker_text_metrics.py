"""AVL-01 — cpWER e cobertura de falante (Frente H1)."""
import pytest

from tests.fidelity.text_metrics import cp_wer, speaker_coverage, wer

pytestmark = pytest.mark.fidelity

REF = {
    "A": "bom dia a todos vamos começar",
    "B": "eu trouxe os números do trimestre",
}


def test_identical_is_zero():
    assert cp_wer(REF, dict(REF)) == 0.0


def test_consistent_label_permutation_is_zero():
    hyp = {"SPEAKER_01": REF["A"], "SPEAKER_00": REF["B"]}
    assert cp_wer(REF, hyp) == 0.0


def test_words_attributed_to_wrong_speaker_count_twice():
    # "vamos começar" foi para B: 2 deleções em A + 2 inserções em B.
    hyp = {
        "X": "bom dia a todos",
        "Y": "vamos começar eu trouxe os números do trimestre",
    }
    assert cp_wer(REF, hyp) == pytest.approx(4 / 12)


def test_single_speaker_hypothesis_deletes_other_speaker():
    hyp = {"X": REF["A"]}
    assert cp_wer(REF, hyp) == pytest.approx(6 / 12)


def test_extra_hypothesis_speaker_counts_insertions():
    hyp = dict(REF, Z="ruído alucinado")
    assert cp_wer(REF, hyp) == pytest.approx(2 / 12)


def test_reduces_to_wer_with_one_speaker():
    ref = {"A": "teste de transcrição local"}
    hyp = {"Q": "teste da transcrição"}
    assert cp_wer(ref, hyp) == pytest.approx(wer(ref["A"], hyp["Q"]))


def test_normalization_applies():
    assert cp_wer({"A": "Transcrição, LOCAL!"}, {"B": "transcricao local"}) == 0.0


def test_empty_reference():
    assert cp_wer({}, {}) == 0.0
    assert cp_wer({"A": ""}, {"B": "algo"}) == 1.0


def test_speaker_coverage():
    assert speaker_coverage([]) == 0.0
    assert speaker_coverage(["A", None, "B", "A"]) == 0.75
