"""IMP-03 — rótulos Participante A, B, C… por ordem de fala."""
import pytest

from src.audio.speaker_labels import friendly_labels, letter_index


def test_letters_follow_first_speech_order():
    seq = ["SPEAKER_01", None, "SPEAKER_00", "SPEAKER_01", "SPEAKER_02"]
    assert friendly_labels(seq) == {
        "SPEAKER_01": "Participante A",
        "SPEAKER_00": "Participante B",
        "SPEAKER_02": "Participante C",
    }


@pytest.mark.parametrize("n,expected", [(0, "A"), (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA")])
def test_letter_index(n, expected):
    assert letter_index(n) == expected


def test_twenty_seventh_speaker_is_AA():
    names = friendly_labels([f"S{i}" for i in range(27)])
    assert names["S26"] == "Participante AA"


def test_numbers_raw_and_custom_prefix():
    assert friendly_labels(["x", "y"], style="numbers") == {"x": "Participante 1", "y": "Participante 2"}
    assert friendly_labels(["x"], style="raw") == {"x": "x"}
    assert friendly_labels(["x", "y"], prefix="Pessoa") == {"x": "Pessoa A", "y": "Pessoa B"}
    assert friendly_labels(["x"], prefix="") == {"x": "A"}


def test_invalid_style():
    with pytest.raises(ValueError):
        friendly_labels(["x"], style="emoji")
