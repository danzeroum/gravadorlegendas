#!/usr/bin/env python3
"""Gera o relatório JSON consolidado de fidelidade de áudio.

Uso:
    python scripts/build_fidelity_report.py \
        --output artifacts/fidelity/report.json

    # reutilizar XML do JUnit de uma execução anterior (CI):
    python scripts/build_fidelity_report.py --output report.json \
        --from-junit junit.xml

    # sem rodar pytest (modo rápido p/ teste de contrato):
    python scripts/build_fidelity_report.py --output report.json --no-pytest

O relatório segue o contrato ``schemas/audio-fidelity-report-v1.json``
(validação automática antes de gravar). Contém apenas informações não
sensíveis: versões de bibliotecas, disponibilidade booleana de recursos,
resultados por teste, métricas observáveis offline e limitações
declaradas — nunca tokens, caminhos de usuário ou logs crus.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "schemas" / "audio-fidelity-report-v1.json"

# Diretórios da suíte offline considerados no relatório.
SUITE_DIRS = [
    "tests/fidelity",
    "tests/golden",
    "tests/contracts",
    "tests/performance",
]

# Classificação honesta por padrão de node-id (com fallback por conteúdo
# do motivo de skip). Mantida explícita e auditável aqui.
CATEGORY_RULES = [
    ("requer-modelo-hf", ("TestStt03", "TestRuido02")),
    ("requer-token-hf", ("TestDia03",)),
]


def _classify_category(classname: str, skip_reason: str | None) -> str:
    for category, patterns in CATEGORY_RULES:
        if any(p in classname for p in patterns):
            return category
    reason = (skip_reason or "").lower()
    if "hf_token" in reason or "hugging" in reason or "token hf" in reason:
        return "requer-token-hf"
    if "modelo" in reason or "whisper" in reason or "espeak" in reason:
        return "requer-modelo-hf"
    if "pipewire" in reason or "wasapi" in reason or "hardware" in reason:
        return "hardware-loopback"
    return "sintetico-offline"


def _safe_name(name: str) -> str:
    """Remove caminhos absolutos/sensíveis do nome do teste."""
    name = name.replace(str(ROOT) + "/", "")
    name = name.replace(str(ROOT), "")
    return name.replace(str(Path.home()), "~")


def parse_junit(path: Path) -> list[dict]:
    """Extrai resultados por teste de um XML JUnit do pytest."""
    tree = ET.parse(str(path))
    results = []
    for case in tree.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        duration = float(case.get("time", "0") or 0)

        status = "passed"
        skip_reason = None
        skipped = case.find("skipped")
        if skipped is not None:
            status = "skipped"
            skip_reason = skipped.get("message") or "skip sem motivo"
        failure = case.find("failure")
        if failure is not None:
            status = "failed"
        error = case.find("error")
        if error is not None:
            status = "error"

        # xfail no JUnit do pytest (xunit2) aparece como <skipped
        # type="pytest.xfail"> — normaliza para status próprio.
        skip_type = (skipped.get("type") or "") if skipped is not None else ""
        if status == "skipped" and (
            skip_type == "pytest.xfail" or "xfail" in (skip_reason or "").lower()
        ):
            status = "xfailed"
            skip_reason = None

        results.append({
            "test_id": _safe_name(f"{classname}::{name}"),
            "test_name": f"{classname.split('.')[-1]}::{name}",
            "status": status,
            "category": _classify_category(classname, skip_reason),
            "metrics": None,
            "thresholds": None,
            "skip_reason": skip_reason if status == "skipped" else None,
            "duration_s": round(duration, 3),
        })
    return results


def run_suite(tmp_xml: Path) -> list[dict]:
    """Roda a suíte offline com JUnit XML e retorna resultados."""
    cmd = [
        sys.executable, "-m", "pytest",
        *SUITE_DIRS,
        "-q", "-p", "no:cacheprovider",
        f"--junitxml={tmp_xml}",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                          text=True, timeout=1800)
    if not tmp_xml.exists():
        raise SystemExit(
            f"pytest não gerou JUnit XML (exit={proc.returncode}):\n"
            f"{proc.stdout[-2000:]}"
        )
    return parse_junit(tmp_xml)


def _lib_version(mod_name: str) -> str:
    """Versão da biblioteca via importlib.metadata (evita deprecação de
    ``__version__`` em pacotes como jsonschema)."""
    try:
        from importlib.metadata import version

        return str(version(mod_name))
    except Exception:
        try:
            mod = __import__(mod_name)
            return str(getattr(mod, "__version__", "ok"))
        except ImportError:
            return "ausente"


def _environment() -> dict:
    """Ambiente não-sensível: versões e disponibilidade de recursos."""
    libs = {}
    for mod_name in ("numpy", "scipy", "soundfile", "jiwer", "hypothesis",
                     "PyYAML", "jsonschema", "structlog",
                     "pyannote.metrics", "faster-whisper"):
        dist = "yaml" if mod_name == "PyYAML" else mod_name
        try:
            __import__(mod_name)
            libs[mod_name] = _lib_version(dist)
        except ImportError:
            libs[mod_name] = "ausente"

    from src.audio.transcribe import whisper_model_dir

    resources = {
        "pw_record": bool(shutil.which("pw-record")),
        "pactl": bool(shutil.which("pactl")),
        "pyaudio": _try_import("pyaudio"),
        "espeak_ng": bool(shutil.which("espeak-ng")),
        "whisper_base_model_cached": whisper_model_dir("base").exists(),
        "pyannote_metrics": _try_import("pyannote.metrics"),
        "diart": _try_import("diart"),
    }
    return {
        "platform": platform.platform(terse=True),
        "python_version": platform.python_version(),
        "cpu_count": __import__("os").cpu_count(),
        "libraries": libs,
        "audio_backends_available": resources,
    }


def _try_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _golden_section() -> dict:
    """Executa o golden verify e resume."""
    import scripts.fidelity_golden as golden_mod

    try:
        ok, diffs, measured = golden_mod.verify()
    except SystemExit as e:
        return {"status": "not-run", "n_scenarios": 0, "diffs": [
            {"scenario": "-", "metric": "golden", "expected": "manifest",
             "measured": str(e)[:200]},
        ]}
    return {
        "status": "verified" if ok else "drifted",
        "n_scenarios": len(measured),
        "diffs": diffs,
    }


def _metrics_summary() -> dict:
    """Métricas objetivas mensuráveis offline nesta execução.

    WER/CER/DER reais dependem de modelo/token — ficam null com
    limitação declarada (nunca omitidas silenciosamente).
    """
    import scripts.fidelity_golden as golden_mod

    summary: dict = {"wer": None, "cer": None, "der": None,
                     "snr_db": None, "drift_s": None, "p95_s": None}
    try:
        _, _, measured = golden_mod.verify()
        sine = measured.get("sine_1k", {})
        summary["sine_spectral_peak_hz"] = sine.get("spectral_peak_hz")
        summary["sine_rms_dbfs"] = sine.get("rms_dbfs")
        clipped = measured.get("clipped", {})
        summary["clipped_fixture_rail_fraction"] = clipped.get(
            "clipped_fraction"
        )
    except SystemExit:
        pass
    # SNR do fixture moderate_noise é mensurável offline (baseline)
    try:
        import numpy as np  # noqa: F401
        import soundfile as sf

        from tests.fidelity import dsp_utils as dsp
        from tests.fixtures import signal_generators as sg

        clean = sg.speech_like(duration_s=5.0, sample_rate=16000, seed=7,
                               amplitude=0.4)
        noisy, _ = sf.read(
            str(ROOT / "tests/fixtures/corpus/audio/moderate_noise.wav"),
            dtype="float64",
        )
        n = min(len(clean), len(noisy))
        summary["snr_db"] = round(dsp.snr_db(clean[:n], noisy[:n]), 2)
    except Exception:
        summary["snr_db"] = None
    return summary


def _default_limitations(results: list[dict]) -> list[str]:
    """Limitações declaradas da execução (nunca vazias)."""
    limitations = [
        "WER/CER humanos exigem corpus consentido — valores de WER aqui "
        "só existem quando faster-whisper + espeak-ng + modelo estão "
        "presentes (categoria requer-modelo-hf).",
        "DER valida harness/métrica/contrato sobre pseudo-fala — não "
        "qualidade de embeddings em vozes humanas.",
        "Testes de hardware/loopback (PipeWire/WASAPI) fazem skip "
        "explícito fora de ambientes com áudio real.",
    ]
    n_model = sum(1 for r in results
                  if r["category"] == "requer-modelo-hf"
                  and r["status"] == "skipped")
    if n_model:
        limitations.append(
            f"{n_model} teste(s) de qualidade com modelo real foram "
            "pulados nesta execução (recurso ausente) — não são sucesso."
        )
    return limitations


def build_report(results: list[dict], golden: dict | None = None,
                 duration_s: float | None = None) -> dict:
    """Monta o dicionário do relatório conforme o schema v1."""
    if golden is None:
        golden = _golden_section()
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0,
              "error": 0}
    for r in results:
        if r["status"] in counts:
            counts[r["status"]] += 1
    try:
        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
    except Exception:
        commit_sha = None

    return {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "commit_sha": commit_sha,
        "environment": _environment(),
        "summary": {
            "total": len(results),
            **counts,
            "duration_s": duration_s,
        },
        "golden": golden,
        "results": results,
        "metrics_summary": _metrics_summary(),
        "limitations": _default_limitations(results),
    }


def validate_schema(report: dict) -> None:
    """Valida o relatório contra o schema versionado (falha alto e claro)."""
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(report, schema)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="caminho do JSON de saída")
    parser.add_argument("--from-junit", type=Path, default=None,
                        help="reutilizar JUnit XML existente")
    parser.add_argument("--no-pytest", action="store_true",
                        help="não rodar pytest (modo rápido de contrato)")
    args = parser.parse_args()

    if args.from_junit:
        results = parse_junit(args.from_junit)
    elif args.no_pytest:
        results = []
    else:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            tmp_xml = Path(f.name)
        try:
            results = run_suite(tmp_xml)
        finally:
            tmp_xml.unlink(missing_ok=True)

    report = build_report(results)
    validate_schema(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    s = report["summary"]
    print(f"Relatório válido gravado: {args.output}")
    print(f"  total={s['total']} passed={s['passed']} failed={s['failed']} "
          f"skipped={s['skipped']} xfailed={s['xfailed']}")
    print(f"  golden={report['golden']['status']}")


if __name__ == "__main__":
    main()
