"""Rótulos amigáveis de falante: "Participante A", "B", "C"… (Frente J).

A diarização devolve IDs locais (``SPEAKER_00``…). Para o usuário, cada
voz vira "Participante A", "Participante B"… na ordem em que fala pela
primeira vez. Os rótulos valem **por arquivo**: o "A" de um arquivo não é a
mesma pessoa do "A" de outro (identificação persistente é a Frente I).
"""
from __future__ import annotations

from typing import Iterable

STYLES = ("letters", "numbers", "raw")


def letter_index(n: int) -> str:
    """0 → A, 25 → Z, 26 → AA, 27 → AB… (como colunas de planilha)."""
    out = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def friendly_labels(speakers: Iterable[str | None], *, style: str = "letters",
                    prefix: str = "Participante") -> dict[str, str]:
    """Rótulo de diarização → nome exibido, na ordem da primeira aparição.

    Args:
        speakers: Rótulos na ordem do tempo (ex.: ``[s.speaker for s in
            segments]``); ``None`` é ignorado.
        style: ``letters`` (Participante A, B…), ``numbers``
            (Participante 1, 2…) ou ``raw`` (mantém ``SPEAKER_00``).
        prefix: Palavra antes da letra/número (vazio = só a letra).
    """
    if style not in STYLES:
        raise ValueError(f"estilo de rótulo inválido: {style!r} (use {', '.join(STYLES)})")
    names: dict[str, str] = {}
    for sp in speakers:
        if sp is None or sp in names:
            continue
        i = len(names)
        if style == "raw":
            names[sp] = sp
            continue
        tag = letter_index(i) if style == "letters" else str(i + 1)
        names[sp] = f"{prefix} {tag}".strip() if prefix else tag
    return names
