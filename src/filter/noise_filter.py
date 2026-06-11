import unicodedata

from src.config import settings


class NoiseFilter:
    def __init__(self, wordlist_path: str | None = None):
        self._wordlist_path = wordlist_path or settings.wordlist_path
        self._wordlist: set[str] | None = None
        self._verb_inflections: set[str] | None = None

    def _remove_accents(self, text: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )

    def _load_wordlist(self) -> set[str]:
        if self._wordlist is not None:
            return self._wordlist
        try:
            with open(self._wordlist_path, "r", encoding="utf-8") as f:
                self._wordlist = {
                    self._remove_accents(line.strip().split()[0].lower())
                    for line in f
                    if line.strip()
                }
        except FileNotFoundError:
            self._wordlist = set()
        return self._wordlist

    def _load_verb_inflections(self, path: str | None = None) -> set[str]:
        if self._verb_inflections is not None:
            return self._verb_inflections
        self._verb_inflections = set()
        if path is None:
            return self._verb_inflections
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._verb_inflections = {
                    self._remove_accents(line.strip().lower())
                    for line in f
                    if line.strip()
                }
        except FileNotFoundError:
            pass
        return self._verb_inflections

    def is_valid(
        self,
        line: str,
        verb_inflections_path: str | None = None,
        min_length: int = 5,
    ) -> bool:
        line = line.strip()
        if len(line) < min_length:
            return False

        wordlist = self._load_wordlist()
        clean_line = self._remove_accents(line.lower())
        words = clean_line.split()
        valid_words = [w for w in words if w in wordlist and len(w) >= 3]

        min_valid = 3
        if len(line) <= 10:
            min_valid = 1
        elif len(line) <= 20:
            min_valid = 2

        if len(valid_words) >= min_valid:
            return True

        if verb_inflections_path:
            verbs = self._load_verb_inflections(verb_inflections_path)
            orig_words = line.lower().split()
            if any(self._remove_accents(w) in verbs for w in orig_words):
                return True

        return False

    def clean_file(
        self,
        input_path: str,
        output_path: str,
        verb_inflections_path: str | None = None,
    ) -> int:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        seen = set()
        good = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            if not self.is_valid(stripped, verb_inflections_path):
                continue

            if good:
                curr_words = stripped.lower().split()
                prev_line = good[-1].strip()
                prev_words = prev_line.lower().split()

                if curr_words[:3] == prev_words[:3]:
                    good.pop()
                    seen.discard(prev_line)
                elif len(set(curr_words) & set(prev_words)) >= 5:
                    good.pop()
                    seen.discard(prev_line)

            good.append(stripped + "\n")
            seen.add(stripped)

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(good)

        return len(good)
