"""Avalia pipelines de diarização num corpus e compara resultados (Frente H1).

Mede DER (e componentes), cpWER e cobertura de falante, por item e no
agregado, e grava um JSON **sem** áudio, texto ou nomes — só IDs e números.
É a única forma aceita de declarar ganho entre frentes (D-023).

Uso:
    # mede o pipeline atual no corpus sintético (o que o CI pode rodar)
    python scripts/eval_diarization.py --corpus tests/fixtures/corpus \\
        --pipeline current --out artifacts/diarizacao/base.json
    # corpus real local (scripts/corpus_real.py)
    python scripts/eval_diarization.py --corpus ~/corpus_real --pipeline offline --out e.json
    # hipóteses externas já em RTTM (outra ferramenta), um <id>.rttm por item
    python scripts/eval_diarization.py --corpus ~/corpus_real --pipeline rttm --hyp-dir saida/
    # compara: sai != 0 se alguma métrica piorar além do limite
    python scripts/eval_diarization.py --compare base.json e.json

Pipelines: ``oracle`` (a própria referência — sanidade do harness),
``rttm`` (hipóteses externas), ``current`` (``DiarizationProcess.diarize_file``)
e ``offline`` (``OfflineDiarizer``, Frente E). Os que dependem de modelo
exigem o extra ``.[diarization]`` e ``HF_TOKEN``; a falha de um item fica
registrada no JSON com o motivo, sem derrubar os demais.

DER exige ``pyannote.metrics`` (extra ``.[diarization-metrics]``, sem torch).
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.rttm import parse_rttm  # noqa: E402

SCHEMA = "gravadorlegendas/diarization-eval@1"
LOWER_IS_BETTER = ("der", "confusion", "false_alarm", "missed", "cp_wer")
HIGHER_IS_BETTER = ("coverage",)


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

def load_corpus(corpus_dir: Path) -> tuple[str, list[dict]]:
    """Lê o manifest sintético (``scenarios``) ou real (``items``).

    Returns:
        (nome do corpus, itens ``{id, audio, rttm, transcript, num_speakers}``
        com caminhos absolutos). Só entram itens com RTTM.
    """
    import yaml

    manifest = yaml.safe_load(
        (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")
    )
    entries = manifest.get("items") or manifest.get("scenarios") or []
    items = []
    for e in entries:
        if not e.get("rttm"):
            continue
        audio = e.get("audio") or e.get("path")
        items.append({
            "id": e["id"],
            "audio": corpus_dir / audio,
            "rttm": corpus_dir / e["rttm"],
            "transcript": (corpus_dir / e["transcript"]
                           if e.get("transcript") else None),
            "num_speakers": e.get("num_speakers") or len(e.get("speakers") or []) or None,
        })
    name = manifest.get("name") or corpus_dir.name
    return name, items


def read_transcript(path: Path) -> dict[str, str]:
    """``FALANTE<TAB>texto`` por linha → falante: texto concatenado."""
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        speaker, text = line.split("\t", 1)
        out.setdefault(speaker.strip(), []).append(text.strip())
    return {k: " ".join(v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# Pipelines: item -> {"turns": [...], "words": [{text, speaker}] | None}
# ---------------------------------------------------------------------------

def _pipeline_oracle(item: dict, opts: argparse.Namespace) -> dict:
    return {"turns": parse_rttm(item["rttm"]), "words": None}


def _pipeline_rttm(item: dict, opts: argparse.Namespace) -> dict:
    if not opts.hyp_dir:
        raise ValueError("--pipeline rttm exige --hyp-dir")
    return {"turns": parse_rttm(Path(opts.hyp_dir) / f"{item['id']}.rttm"),
            "words": None}


def _pipeline_current(item: dict, opts: argparse.Namespace) -> dict:
    import multiprocessing

    from src.audio.diarize import DiarizationProcess

    errors: multiprocessing.Queue = multiprocessing.Queue()
    dp = DiarizationProcess(multiprocessing.Queue(), errors)
    turns = dp.diarize_file(str(item["audio"]))
    if not turns:
        # O erro chega pela fila (feeder thread assíncrona): espera um pouco.
        try:
            msg = errors.get(timeout=1.0).get("error", "falha sem detalhe")
        except Exception:
            msg = "diarize_file não retornou segmentos"
        raise RuntimeError(msg)
    return {"turns": turns, "words": None}


def _pipeline_offline(item: dict, opts: argparse.Namespace) -> dict:
    from src.audio.offline_diarizer import OfflineDiarizer

    diarizer = OfflineDiarizer()
    diarizer.check_ready()
    turns = diarizer.diarize(
        str(item["audio"]),
        num_speakers=item["num_speakers"] if opts.oracle_num_speakers else None,
    )
    return {"turns": [{"speaker": t.speaker, "start": t.start, "end": t.end}
                      for t in turns],
            "words": None}


PIPELINES: dict[str, Callable[[dict, argparse.Namespace], dict]] = {
    "oracle": _pipeline_oracle,
    "rttm": _pipeline_rttm,
    "current": _pipeline_current,
    "offline": _pipeline_offline,
}


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def _annotation(segments: list[dict], uri: str):
    from pyannote.core import Annotation, Segment

    ann = Annotation(uri=uri)
    for s in segments:
        if s["end"] > s["start"]:
            ann[Segment(s["start"], s["end"])] = s["speaker"]
    return ann


def der_components(ref: list[dict], hyp: list[dict], uri: str = "x") -> dict:
    """Componentes absolutos (segundos) do DER, collar 0 e overlap contado."""
    try:
        from pyannote.metrics.diarization import DiarizationErrorRate
    except ImportError as e:
        raise RuntimeError(
            "pyannote.metrics ausente: pip install -e \".[diarization-metrics]\""
        ) from e
    metric = DiarizationErrorRate(collar=0.0, skip_overlap=False)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*'uem' was approximated.*")
        d = metric(_annotation(ref, uri), _annotation(hyp, uri), detailed=True)
    return {
        "total": float(d["total"]),
        "confusion": float(d["confusion"]),
        "false_alarm": float(d["false alarm"]),
        "missed": float(d["missed detection"]),
    }


def _rates(c: dict) -> dict:
    total = c["total"]
    if total <= 0:
        return {"der": 0.0, "confusion": 0.0, "false_alarm": 0.0, "missed": 0.0}
    return {
        "der": (c["confusion"] + c["false_alarm"] + c["missed"]) / total,
        "confusion": c["confusion"] / total,
        "false_alarm": c["false_alarm"] / total,
        "missed": c["missed"] / total,
    }


def evaluate_item(item: dict, result: dict) -> dict:
    ref = parse_rttm(item["rttm"])
    hyp = result["turns"]
    comps = der_components(ref, hyp, uri=item["id"])
    row = {
        "id": item["id"],
        "status": "ok",
        **{k: round(v, 4) for k, v in _rates(comps).items()},
        "_components": comps,
        "num_speakers_ref": len({s["speaker"] for s in ref}),
        "num_speakers_hyp": len({s["speaker"] for s in hyp}),
    }
    words = result.get("words")
    if words is not None:
        from tests.fidelity.text_metrics import cp_wer, speaker_coverage

        row["coverage"] = round(speaker_coverage([w["speaker"] for w in words]), 4)
        if item.get("transcript"):
            hyp_text: dict[str, list[str]] = {}
            for w in words:
                # Palavra sem falante não pertence a ninguém: conta como
                # deleção no falante certo (cobertura mede a parte que falta).
                if w["speaker"] is not None:
                    hyp_text.setdefault(str(w["speaker"]), []).append(w["text"])
            row["cp_wer"] = round(cp_wer(
                read_transcript(item["transcript"]),
                {k: " ".join(v) for k, v in hyp_text.items()},
            ), 4)
    return row


def aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    agg: dict = {"items_ok": len(ok), "items_error": len(rows) - len(ok)}
    if not ok:
        return agg
    summed = {k: sum(r["_components"][k] for r in ok)
              for k in ("total", "confusion", "false_alarm", "missed")}
    agg.update({k: round(v, 4) for k, v in _rates(summed).items()})
    for key in ("cp_wer", "coverage"):
        vals = [r[key] for r in ok if key in r]
        if vals:
            agg[key] = round(sum(vals) / len(vals), 4)
    return agg


def run(corpus_dir: Path, pipeline: str, opts: argparse.Namespace) -> dict:
    name, items = load_corpus(corpus_dir)
    fn = PIPELINES[pipeline]
    rows = []
    for item in items:
        t0 = time.monotonic()
        try:
            row = evaluate_item(item, fn(item, opts))
        except Exception as e:
            row = {"id": item["id"], "status": "error",
                   "error": f"{type(e).__name__}: {e}"[:300]}
        row["seconds"] = round(time.monotonic() - t0, 2)
        rows.append(row)
    report = {
        "schema": SCHEMA,
        "pipeline": pipeline,
        "corpus": name,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"python": platform.python_version(),
                        "platform": platform.system()},
        "aggregate": aggregate(rows),
        "items": rows,
    }
    for r in rows:
        r.pop("_components", None)
    return report


# ---------------------------------------------------------------------------
# Comparação
# ---------------------------------------------------------------------------

def compare(before: dict, after: dict, max_regression: float = 0.01) -> tuple[str, bool]:
    """Tabela de delta do agregado e se houve regressão além do limite."""
    a, b = before["aggregate"], after["aggregate"]
    lines = [
        f"{'métrica':<12} {before['pipeline']:>12} {after['pipeline']:>12} {'delta':>9}",
    ]
    regressed = False
    for key in LOWER_IS_BETTER + HIGHER_IS_BETTER:
        if key not in a or key not in b:
            continue
        delta = b[key] - a[key]
        worse = delta > max_regression if key in LOWER_IS_BETTER \
            else -delta > max_regression
        regressed |= worse
        flag = "  PIOROU" if worse else ""
        lines.append(f"{key:<12} {a[key]:>12.4f} {b[key]:>12.4f} {delta:>+9.4f}{flag}")
    if a.get("items_error") or b.get("items_error"):
        lines.append(f"itens com erro: {a.get('items_error', 0)} -> {b.get('items_error', 0)}")
    return "\n".join(lines), regressed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--pipeline", choices=sorted(PIPELINES), default="current")
    parser.add_argument("--hyp-dir", type=Path, help="RTTMs de hipótese (--pipeline rttm)")
    parser.add_argument("--oracle-num-speakers", action="store_true",
                        help="passa o nº real de falantes ao diarizador")
    parser.add_argument("--out", type=Path, help="JSON de saída")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("ANTES", "DEPOIS"))
    parser.add_argument("--max-regression", type=float, default=0.01)
    args = parser.parse_args(argv)

    if args.compare:
        before, after = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        table, regressed = compare(before, after, args.max_regression)
        print(table)
        return 1 if regressed else 0

    if not args.corpus:
        parser.error("--corpus é obrigatório (ou use --compare)")
    report = run(args.corpus, args.pipeline, args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    agg = report["aggregate"]
    print(f"pipeline={args.pipeline} corpus={report['corpus']} "
          f"ok={agg['items_ok']} erro={agg['items_error']}")
    for key in LOWER_IS_BETTER + HIGHER_IS_BETTER:
        if key in agg:
            print(f"  {key}: {agg[key]:.4f}")
    for row in report["items"]:
        if row["status"] == "error":
            print(f"  ERRO {row['id']}: {row['error']}")
    return 0 if agg["items_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
