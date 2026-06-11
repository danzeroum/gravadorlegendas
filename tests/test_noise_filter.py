import tempfile
from pathlib import Path

from src.filter.noise_filter import NoiseFilter


def _make_wordlist(words: list[str]) -> str:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.writelines(w + "\n" for w in words)
        return f.name


class TestNoiseFilter:
    def test_is_valid_short_line(self):
        nf = NoiseFilter(_make_wordlist(["a", "b"]))
        assert nf.is_valid("ab", min_length=5) is False

    def test_is_valid_with_valid_words(self):
        wl = _make_wordlist(["hello", "world", "test", "this", "is"])
        nf = NoiseFilter(wl)
        assert nf.is_valid("hello world test", min_length=3) is True

    def test_is_valid_without_enough_valid_words(self):
        wl = _make_wordlist(["hello"])
        nf = NoiseFilter(wl)
        assert nf.is_valid("hello xyzzy unknown garbage", min_length=5) is False

    def test_clean_file_empty_input(self):
        wl = _make_wordlist(["hello", "world"])
        nf = NoiseFilter(wl)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as inp:
            inp.write("")
            inp_path = inp.name
        out_path = inp_path + "_out"
        count = nf.clean_file(inp_path, out_path)
        assert count == 0

    def test_clean_file_removes_duplicates(self):
        wl = _make_wordlist(["hello", "world", "test"])
        nf = NoiseFilter(wl)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as inp:
            inp.write("hello world test\nhello world test\n")
            inp_path = inp.name
        out_path = inp_path + "_out"
        count = nf.clean_file(inp_path, out_path)
        assert count == 1
