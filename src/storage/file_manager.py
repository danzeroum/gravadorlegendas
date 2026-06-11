import os
from datetime import datetime

from src.config import settings


class FileManager:
    def __init__(self, directory: str | None = None):
        self._directory = directory or settings.recording_dir
        os.makedirs(self._directory, exist_ok=True)

    def build_path(self, prefix: str, suffix: str = "") -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{prefix}_{timestamp}{suffix}.txt"
        return os.path.join(self._directory, filename)

    def save_line(self, path: str, line: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_all(self, path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def clean_and_sort(self, input_path: str, output_path: str) -> int:
        with open(input_path, "r", encoding="utf-8") as f:
            words = {line.strip().lower() for line in f if line.strip()}
        sorted_words = sorted(words)
        with open(output_path, "w", encoding="utf-8") as f:
            for w in sorted_words:
                f.write(w + "\n")
        return len(sorted_words)
