"""Leitura e escrita de RTTM (NIST) — "quem falou quando".

Formato de linha: ``SPEAKER <uri> 1 <inicio> <duracao> <NA> <NA> <falante> <NA> <NA>``.
Usado pelo corpus real e pelo avaliador de diarização (docs/diarizacao).
"""
from __future__ import annotations

from pathlib import Path


def parse_rttm_text(text: str) -> list[dict]:
    """Linhas RTTM → ``[{speaker, start, end}]`` (ignora não-SPEAKER)."""
    segments = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0] == "SPEAKER":
            start = float(parts[3])
            segments.append({
                "speaker": parts[7],
                "start": start,
                "end": start + float(parts[4]),
            })
    return segments


def parse_rttm(path: str | Path) -> list[dict]:
    """Lê um arquivo RTTM (UTF-8)."""
    return parse_rttm_text(Path(path).read_text(encoding="utf-8"))


def format_rttm(segments: list[dict], uri: str) -> str:
    """``[{speaker, start, end}]`` → texto RTTM."""
    lines = [
        f"SPEAKER {uri} 1 {s['start']:.3f} {s['end'] - s['start']:.3f} "
        f"<NA> <NA> {s['speaker']} <NA> <NA>"
        for s in segments
    ]
    return "\n".join(lines) + ("\n" if lines else "")
