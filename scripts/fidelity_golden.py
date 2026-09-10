#!/usr/bin/env python3
"""Golden master de fidelidade de áudio — verify/freeze deliberado.

Uso:
    python scripts/fidelity_golden.py verify
        Verifica as medições estáveis do corpus contra a baseline
        congelada (tests/golden/manifest.yaml). Falha com diff claro.

    python scripts/fidelity_golden.py freeze --confirm-golden-regen
        REGENERAR a baseline. FALHA sem a flag --confirm-golden-regen:
        atualização de golden é ação deliberada, rastreável em commit/PR
        com a convenção ``golden-regen`` (ver política em
        docs/qualidade-audio/README.md §7).

O golden guarda SOMENTE medições estáveis: sha256 da fixture, contagem
de samples, duração, RMS (dBFS), pico espectral, DC offset e fração de
clipping — NUNCA wall-clock, jitter absoluto ou caminhos de máquina.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fidelity import dsp_utils as dsp  # noqa: E402

GOLDEN_DIR = ROOT / "tests" / "golden"
GOLDEN_MANIFEST = GOLDEN_DIR / "manifest.yaml"
CORPUS_DIR = ROOT / "tests" / "fixtures" / "corpus"
CORPUS_MANIFEST = CORPUS_DIR / "manifest.yaml"

GOLDEN_SCHEMA = "gravadorlegendas/golden@1"

# Tolerâncias derivadas de variância NUMÉRICA (float64/FFT), não de tempo:
# WAVs são determinísticos por seed; tolerâncias absorvem micro-variantes
# entre versões de numpy/libsndfile/FFT enquanto detectam mudanças reais
# (ganho > 0.05 dB, deriva de frequência > 0.5 Hz, perda de samples).
DEFAULT_TOLERANCES = {
    "rms_dbfs": 0.05,
    "spectral_peak_hz": 0.5,
    "dc_offset_abs": 1.0e-5,
    "clipped_fraction_abs": 1.0e-5,
    "n_samples": 0,
    "sha256": "exact",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def measure_scenario(wav_path: Path) -> dict:
    """Mede as propriedades estáveis de um fixture do corpus."""
    x, sr = sf.read(str(wav_path), dtype="float64")
    n = int(len(x))
    rms_db = dsp.rms_dbfs(x)
    peak_hz = dsp.spectral_peak_hz(x, sr) if rms_db > float("-inf") else None
    return {
        "sample_rate": int(sr),
        "n_samples": n,
        "duration_s": round(n / sr, 3),
        "rms_dbfs": round(rms_db, 4) if rms_db > float("-inf") else None,
        "spectral_peak_hz": round(peak_hz, 2) if peak_hz is not None else None,
        "dc_offset": round(dsp.dc_offset(x), 6),
        "clipped_fraction": round(dsp.clipped_fraction(x), 6),
        "sha256": _sha256_file(wav_path),
    }


def measure_corpus(corpus_dir: Path = CORPUS_DIR) -> dict:
    """Mede todos os fixtures do corpus (caminho -> medições)."""
    import yaml

    with open(corpus_dir / "manifest.yaml", encoding="utf-8") as f:
        corpus = yaml.safe_load(f)
    out = {}
    for scen in corpus["scenarios"]:
        wav = corpus_dir / scen["path"]
        out[scen["id"]] = measure_scenario(wav)
    return out


def _load_golden(path: Path = GOLDEN_MANIFEST) -> dict:
    import yaml

    if not path.exists():
        raise SystemExit(
            f"Golden manifest não encontrado: {path}\n"
            "Congele a baseline com: python scripts/fidelity_golden.py "
            "freeze --confirm-golden-regen"
        )
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compare(golden: dict, measured: dict, tolerances: dict) -> list:
    """Compara medições contra golden; retorna lista de diffs."""
    diffs = []
    for scen, gold_vals in golden.items():
        meas = measured.get(scen)
        if meas is None:
            diffs.append({
                "scenario": scen, "metric": "presence",
                "expected": "fixture presente", "measured": "AUSENTE",
            })
            continue
        for metric, tol in (
            ("n_samples", tolerances["n_samples"]),
            ("sha256", tolerances["sha256"]),
            ("rms_dbfs", tolerances["rms_dbfs"]),
            ("spectral_peak_hz", tolerances["spectral_peak_hz"]),
            ("dc_offset", tolerances["dc_offset_abs"]),
            ("clipped_fraction", tolerances["clipped_fraction_abs"]),
        ):
            g = gold_vals.get(metric)
            m = meas.get(metric)
            if g is None and m is None:
                continue
            if metric == "sha256":
                ok = g == m
            elif metric == "n_samples":
                ok = abs((m or 0) - (g or 0)) <= tol
            else:
                ok = abs((m or 0.0) - (g or 0.0)) <= tol
            if not ok:
                diffs.append({
                    "scenario": scen, "metric": metric,
                    "expected": g, "measured": m,
                })
    for scen in measured:
        if scen not in golden:
            diffs.append({
                "scenario": scen, "metric": "presence",
                "expected": "não congelado", "measured": "NOVO fixture",
            })
    return diffs


def verify(golden_path: Path = GOLDEN_MANIFEST,
           corpus_dir: Path = CORPUS_DIR) -> tuple[bool, list, dict]:
    """Verifica corpus contra golden. Retorna (ok, diffs, medidas)."""
    golden_data = _load_golden(golden_path)
    measured = measure_corpus(corpus_dir)
    diffs = _compare(golden_data["scenarios"], measured,
                     golden_data.get("tolerances", DEFAULT_TOLERANCES))
    return (not diffs), diffs, measured


def freeze(confirm: bool, golden_path: Path = GOLDEN_MANIFEST,
           corpus_dir: Path = CORPUS_DIR) -> None:
    """Regenera a baseline golden — exige confirmação explícita."""
    if not confirm:
        raise SystemExit(
            "RECUSADO: freeze sem --confirm-golden-regen.\n"
            "Atualizar golden é ação deliberada: justifique no commit/PR "
            "usando a convenção 'golden-regen' (política em "
            "docs/qualidade-audio/README.md §7)."
        )
    import yaml

    measured = measure_corpus(corpus_dir)
    golden = {
        "schema": GOLDEN_SCHEMA,
        "frozen_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "generator": "tests/fixtures/signal_generators.py",
        "generator_version": 1,
        "regenerate": (
            "python scripts/fidelity_golden.py freeze "
            "--confirm-golden-regen"
        ),
        "policy": (
            "Golden guarda SOMENTE medições estáveis (sha256, samples, "
            "duração, RMS dBFS, pico espectral, DC offset, clipping). "
            "Wall-clock/jitter NUNCA são congelados. Tolerâncias por "
            "métrica derivadas de variância numérica float64/FFT — "
            "calibração no manifesto do corpus."
        ),
        "tolerances": DEFAULT_TOLERANCES,
        "scenarios": measured,
    }
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    with open(golden_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(golden, f, allow_unicode=True, sort_keys=True,
                       width=100)
    print(f"Golden congelado: {golden_path}")
    print(f"Cenários: {len(measured)}")
    print("Lembre-se: commit com convenção 'golden-regen' + justificativa.")


def _print_diffs(diffs: list) -> None:
    print(f"\nGOLDEN DRIFT — {len(diffs)} divergência(s):")
    for d in diffs:
        print(f"  [{d['scenario']}] {d['metric']}: "
              f"esperado {d['expected']!r} != medido {d['measured']!r}")
    print("\nSe a mudança for intencional: "
          "python scripts/fidelity_golden.py freeze "
          "--confirm-golden-regen + convenção 'golden-regen' no commit.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify", help="verificar corpus contra golden")

    p_freeze = sub.add_parser("freeze", help="regenerar golden (deliberado)")
    p_freeze.add_argument(
        "--confirm-golden-regen", action="store_true",
        help="confirmação explícita de regeneração da baseline",
    )

    args = parser.parse_args()

    if args.command == "verify":
        ok, diffs, _ = verify()
        if ok:
            print("GOLDEN VERIFIED: corpus íntegro contra a baseline.")
        else:
            _print_diffs(diffs)
            sys.exit(1)
    elif args.command == "freeze":
        freeze(confirm=args.confirm_golden_regen)


if __name__ == "__main__":
    main()
