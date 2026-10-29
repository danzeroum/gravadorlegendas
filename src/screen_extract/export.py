"""Saída: .json (dados), .csv (Excel pt-BR) e .md (legível)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.screen_extract.models import Item
from src.storage.subtitle_exporter import format_clock

CSV_COLUMNS = ("tipo", "pergunta", "texto", "marcado", "primeira_vez",
               "ultima_vez", "vezes_visto", "mudancas")
_FORMULA_START = ("=", "+", "-", "@")


def _estado(item: Item) -> str:
    return "" if item.marcado is None else ("sim" if item.marcado else "não")


def _safe(cell: str) -> str:
    """Evita que o Excel interprete texto lido do vídeo como fórmula."""
    return "'" + cell if cell.startswith(_FORMULA_START) else cell


def to_dict(items: list[Item], arquivo: str, meta: dict) -> dict:
    return {
        "arquivo": arquivo,
        **meta,
        "itens": [{
            "tipo": i.tipo, "pergunta": i.pergunta, "texto": i.texto,
            "marcado": i.marcado, "primeira_vez": round(i.primeira_vez, 1),
            "ultima_vez": round(i.ultima_vez, 1), "vezes_visto": i.vezes_visto,
            "mudancas": [[round(t, 1), m] for t, m in i.mudancas],
        } for i in items],
    }


def to_csv(items: list[Item], path: Path) -> None:
    # utf-8-sig + ';' para abrir direto no Excel em português.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CSV_COLUMNS)
        for i in items:
            w.writerow([
                i.tipo, _safe(i.pergunta), _safe(i.texto), _estado(i),
                format_clock(i.primeira_vez), format_clock(i.ultima_vez),
                i.vezes_visto,
                " | ".join(f"{format_clock(t)}={'sim' if m else 'não'}"
                           for t, m in i.mudancas if m is not None),
            ])


def to_markdown(items: list[Item], arquivo: str, meta: dict) -> str:
    lines = [f"# Respostas lidas da tela — {arquivo}", "",
             f"- Frames analisados: {meta.get('frames_analisados', '?')} "
             f"(mantidos {meta.get('frames_mantidos', '?')}, "
             f"borrados descartados {meta.get('frames_borrados', '?')})",
             "- Só aparece o que foi mostrado na tela; itens nunca exibidos "
             "(listas não roladas) ficam de fora. Confira por amostragem: OCR "
             "e detecção de caixa marcada podem errar.", ""]
    atual = None
    for i in items:
        if i.tipo == "pergunta":
            lines += ["", f"## {i.texto}  _({format_clock(i.primeira_vez)})_"]
            atual = i.texto
            continue
        if i.pergunta != atual:
            atual = i.pergunta
            lines += ["", f"## {i.pergunta or '(sem pergunta identificada)'}"]
        box = {True: "[x]", False: "[ ]", None: "-"}[i.marcado]
        lines.append(f"- {box} {i.texto}  _({format_clock(i.ultima_vez)})_")
    return "\n".join(lines) + "\n"


def save_all(items: list[Item], out_dir: Path, stem: str, arquivo: str,
             meta: dict) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {ext: out_dir / f"{stem}_tela.{ext}" for ext in ("json", "csv", "md")}
    paths["json"].write_text(
        json.dumps(to_dict(items, arquivo, meta), ensure_ascii=False, indent=2),
        encoding="utf-8")
    to_csv(items, paths["csv"])
    paths["md"].write_text(to_markdown(items, arquivo, meta), encoding="utf-8")
    return paths
