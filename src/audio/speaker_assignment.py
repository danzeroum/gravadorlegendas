"""Atribuição de falante por palavra (Frente F do plano de diarização).

Cruza os timestamps por palavra do Whisper com os turnos da diarização:
cada palavra recebe o falante do turno que contém o seu **ponto médio**.
Substitui o casamento por lote inteiro (~7 s), que dava um único rótulo
para um trecho com várias pessoas (ACH-03).

Funções puras, sem dependências pesadas — usadas no reprocessamento
offline, na importação de arquivos e (best effort) na transcrição ao vivo.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Iterable

from src.audio.models import CaptionSegment


@dataclass(frozen=True)
class Word:
    """Palavra transcrita com tempo absoluto (segundos).

    ``text`` mantém o espaço inicial do Whisper (marca de início de palavra).
    """

    start: float
    end: float
    text: str


def _turn_fields(turn) -> tuple[str, float, float]:
    """Aceita ``SpeakerTurn`` ou dict ``{speaker, start, end}``."""
    if isinstance(turn, dict):
        return str(turn["speaker"]), float(turn["start"]), float(turn["end"])
    return str(turn.speaker), float(turn.start), float(turn.end)


def assign_words(words: Iterable[Word], turns: Iterable, *,
                 tolerance: float = 0.3) -> list[tuple[Word, str | None]]:
    """Falante de cada palavra pelo ponto médio.

    Regras:
    - turno que contém o ponto médio; se mais de um (fala sobreposta),
      o que começou por último (mesma regra de ``make_exclusive``);
    - nenhum contém: o turno mais próximo, se a distância for até
      ``tolerance`` segundos (pausas curtas entre turnos);
    - senão ``None`` (sem rótulo — conta contra a cobertura).

    Complexidade O((n + m) log m) para n palavras e m turnos.
    """
    spans = sorted(
        (t for t in (_turn_fields(x) for x in turns) if t[2] > t[1]),
        key=lambda t: (t[1], t[2]),
    )
    starts = [s for _, s, _ in spans]
    # prefix_end[i] = (maior fim entre spans[0..i], índice do dono)
    prefix_end: list[tuple[float, int]] = []
    for i, (_, _, end) in enumerate(spans):
        if not prefix_end or end > prefix_end[-1][0]:
            prefix_end.append((end, i))
        else:
            prefix_end.append(prefix_end[-1])

    out: list[tuple[Word, str | None]] = []
    for w in words:
        mid = (w.start + w.end) / 2.0
        idx = bisect.bisect_right(starts, mid)  # spans[:idx] começam <= mid
        speaker = None
        # Contém: varre para trás enquanto algum turno anterior ainda
        # pode terminar depois do ponto médio.
        j = idx - 1
        while j >= 0 and prefix_end[j][0] >= mid:
            sp, s, e = spans[j]
            if s <= mid <= e:
                speaker = sp
                break
            j -= 1
        if speaker is None and spans:
            best, best_dist = None, tolerance
            if idx > 0:
                end, owner = prefix_end[idx - 1]
                if mid - end <= best_dist:
                    best, best_dist = spans[owner][0], mid - end
            if idx < len(spans) and starts[idx] - mid <= best_dist:
                best = spans[idx][0]
            speaker = best
        out.append((w, speaker))
    return out


def join_words(texts: list[str]) -> str:
    """Junta textos de palavras em uma frase.

    O Whisper marca início de palavra com espaço à esquerda (``" dia"``) e
    continuação sem espaço (``"-ci"``, pedaço da mesma palavra). Se as
    palavras trazem essa marcação, concatena preservando-a; se nenhuma traz
    (outra fonte), separa por espaço.
    """
    texts = [t for t in texts if t.strip()]
    if any(t[:1].isspace() for t in texts[1:]):
        return "".join(texts).strip()
    return " ".join(t.strip() for t in texts)


def group_segments(assigned: list[tuple[Word, str | None]], *,
                   max_gap: float = 1.0,
                   max_duration: float = 7.0) -> list[CaptionSegment]:
    """Agrupa palavras consecutivas do mesmo falante em legendas.

    Quebra o grupo na troca de falante, numa pausa maior que ``max_gap`` ou
    quando a legenda passaria de ``max_duration`` segundos. Palavra sem
    falante (``None``) não quebra o grupo corrente — fica com quem estava
    falando; um grupo que começa sem falante adota o primeiro rótulo que
    aparecer.
    """
    segments: list[CaptionSegment] = []
    group: list[Word] = []
    speaker: str | None = None

    def flush():
        text = join_words([w.text for w in group])
        if text and group[-1].end > group[0].start:
            segments.append(CaptionSegment(
                start=group[0].start, end=group[-1].end, text=text,
                speaker=speaker,
            ))

    for word, sp in assigned:
        if not word.text.strip():
            continue
        if group:
            speaker_change = sp is not None and speaker is not None and sp != speaker
            gap = word.start - group[-1].end > max_gap
            too_long = word.end - group[0].start > max_duration
            if speaker_change or gap or too_long:
                flush()
                group, speaker = [], None
        group.append(word)
        if speaker is None:
            speaker = sp
    if group:
        flush()
    return segments
