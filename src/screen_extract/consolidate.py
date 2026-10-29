"""Consolida as leituras: guarda o último estado visto de cada item."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from src.screen_extract.models import Item, Leitura, Linha

SIMILARITY = 0.88    # linhas com OCR levemente diferente contam como a mesma
_NUMBERED = re.compile(r"^\s*\d+(\.\d+)*[.)]?\s+\S")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return " ".join("".join(c for c in text if c.isalnum() or c.isspace()).split())


def is_question(linha: Linha) -> bool:
    """Pergunta: sem caixa de seleção e terminada em '?' ou numerada ('1.2) …')."""
    if linha.marcado is not None:
        return False
    t = linha.texto.strip()
    return t.endswith("?") or bool(_NUMBERED.match(t))


def _same(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= SIMILARITY


def consolidate(leituras: list[Leitura]) -> list[Item]:
    """Junta por (pergunta, texto) mantendo ordem da 1ª aparição.

    A pergunta "atual" atravessa os frames: ao rolar, as opções no topo do
    frame seguinte continuam pertencendo à última pergunta vista.
    """
    items: list[Item] = []
    keys: list[tuple[str, str, str]] = []   # (tipo, pergunta_norm, texto_norm)
    current = ""
    current_norm = ""

    def find(tipo: str, pq: str, tx: str) -> int | None:
        for i, (t, p, x) in enumerate(keys):
            if t == tipo and _same(p, pq) and _same(x, tx):
                return i
        return None

    for leitura in sorted(leituras, key=lambda r: r.t):
        for linha in leitura.linhas:
            texto = linha.texto.strip()
            tx = norm(texto)
            if not tx:
                continue
            if is_question(linha):
                tipo, pergunta, pq = "pergunta", "", ""
                i = find(tipo, pq, tx)
                if i is not None:
                    current, current_norm = items[i].texto, keys[i][2]
                else:
                    current, current_norm = texto, tx
            else:
                tipo = "opcao" if linha.marcado is not None else "texto"
                pergunta, pq = current, current_norm
                i = find(tipo, pq, tx)

            if i is None:
                items.append(Item(tipo, texto, pergunta, linha.marcado,
                                  leitura.t, leitura.t, 1,
                                  [(leitura.t, linha.marcado)] if linha.marcado is not None else []))
                keys.append((tipo, pq, tx))
                continue
            item = items[i]
            item.ultima_vez = leitura.t
            item.vezes_visto += 1
            if linha.marcado is not None and linha.marcado != item.marcado:
                item.mudancas.append((leitura.t, linha.marcado))
                item.marcado = linha.marcado
    return items
