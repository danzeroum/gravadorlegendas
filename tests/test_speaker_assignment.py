"""ALN-01..03 — atribuição de falante por palavra (Frente F)."""
import time

import pytest

from src.audio.offline_diarizer import SpeakerTurn
from src.audio.speaker_assignment import Word, assign_words, group_segments

TURNS = [SpeakerTurn("A", 0.0, 2.0), SpeakerTurn("B", 2.0, 4.0),
         SpeakerTurn("A", 6.0, 8.0)]


def W(a, b, t="x"):
    return Word(a, b, t)


def speakers(words, turns=TURNS, **kw):
    return [sp for _, sp in assign_words(words, turns, **kw)]


def test_midpoint_decides():
    # 1.8–2.4: ponto médio 2.1 está em B, mesmo começando em A.
    assert speakers([W(0.2, 0.6), W(1.8, 2.4), W(3.0, 3.5)]) == ["A", "B", "B"]


def test_boundary_goes_to_later_starter():
    assert speakers([W(1.9, 2.1)]) == ["B"]


def test_short_gap_uses_tolerance_and_long_gap_is_none():
    # gap 4.0–6.0: 4.1 está a 0.1 s de B; 5.0 está a 1 s de tudo.
    assert speakers([W(4.05, 4.15), W(4.9, 5.1), W(5.85, 5.95)]) == ["B", None, "A"]


def test_tolerance_zero_disables_nearest():
    assert speakers([W(4.05, 4.15)], tolerance=0.0) == [None]


def test_overlapping_turns_pick_latest_start_and_unsorted_input():
    turns = [SpeakerTurn("B", 3.0, 4.0), {"speaker": "A", "start": 0.0, "end": 10.0}]
    assert speakers([W(1, 1.2), W(3.4, 3.6), W(5, 5.2)], turns) == ["A", "B", "A"]


def test_no_turns_means_no_speaker():
    assert speakers([W(0, 1)], []) == [None]


def test_scales_to_ten_thousand_words():
    turns = [SpeakerTurn("AB"[i % 2], i * 3.0, i * 3.0 + 2.5) for i in range(2000)]
    words = [W(i * 0.6, i * 0.6 + 0.3) for i in range(10_000)]
    t0 = time.perf_counter()
    out = assign_words(words, turns)
    assert len(out) == 10_000
    assert time.perf_counter() - t0 < 0.5


# --- group_segments ---------------------------------------------------------

def test_group_breaks_on_speaker_change_and_keeps_text_order():
    assigned = [(W(0.0, 0.4, " Bom"), "A"), (W(0.5, 0.9, " dia."), "A"),
                (W(1.0, 1.3, " Oi,"), "B"), (W(1.4, 1.8, " tudo?"), "B")]
    segs = group_segments(assigned)
    assert [(s.speaker, s.text, s.start, s.end) for s in segs] == [
        ("A", "Bom dia.", 0.0, 0.9), ("B", "Oi, tudo?", 1.0, 1.8),
    ]


def test_group_breaks_on_long_pause_and_max_duration():
    pause = [(W(0, 0.5, "a"), "A"), (W(2.0, 2.5, "b"), "A")]
    assert len(group_segments(pause, max_gap=1.0)) == 2
    long_run = [(W(i, i + 0.9, "w"), "A") for i in range(10)]
    segs = group_segments(long_run, max_duration=3.0)
    assert all(s.end - s.start <= 3.0 for s in segs) and len(segs) == 4


def test_unlabeled_word_does_not_split_and_group_adopts_first_label():
    assigned = [(W(0, 0.4, "eu"), None), (W(0.5, 0.9, "acho"), "A"),
                (W(1.0, 1.4, "que"), None), (W(1.5, 1.9, "sim"), "A")]
    segs = group_segments(assigned)
    assert len(segs) == 1 and segs[0].speaker == "A"
    assert segs[0].text == "eu acho que sim"


def test_empty_words_skipped():
    assert group_segments([(W(0, 1, "  "), "A")]) == []


def test_regression_batch_with_two_speakers_gets_two_labels():
    """ACH-03: um lote de 7 s com duas pessoas recebia um rótulo só."""
    turns = [SpeakerTurn("SPEAKER_00", 0.0, 3.4), SpeakerTurn("SPEAKER_01", 3.6, 7.0)]
    words = [W(0.2 + i * 0.5, 0.6 + i * 0.5, f"w{i}") for i in range(13)]
    segs = group_segments(assign_words(words, turns))
    assert [s.speaker for s in segs] == ["SPEAKER_00", "SPEAKER_01"]
    assert pytest.approx(segs[1].start) == 3.7
