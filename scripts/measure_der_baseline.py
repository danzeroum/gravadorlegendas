"""Calibra DER esperado para transformações controladas do RTTM.

Medição de baseline para thresholds do manifesto (executa uma vez).
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")  # noqa: E402

from pyannote.core import Annotation, Segment  # noqa: E402
from pyannote.metrics.diarization import DiarizationErrorRate  # noqa: E402

CORPUS = Path("tests/fixtures/corpus")


def parse_rttm(path: Path):
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0] == "SPEAKER":
            segments.append({
                "speaker": parts[7], "start": float(parts[3]),
                "end": float(parts[3]) + float(parts[4]),
            })
    return segments


def to_annotation(segments, uri="calib"):
    ann = Annotation(uri=uri)
    for s in segments:
        ann[Segment(s["start"], s["end"])] = s["speaker"]
    return ann


def measure(name, ref_segs, hyp_segs):
    der_metric = DiarizationErrorRate(collar=0.0, skip_overlap=False)
    value = der_metric(to_annotation(ref_segs), to_annotation(hyp_segs))
    print(f"{name}: DER={value:.4f}")
    return value


for scen in ("two_speakers_no_overlap", "two_speakers_overlap",
             "three_speakers", "speaker_enter_exit"):
    ref = parse_rttm(CORPUS / "rttm" / f"{scen}.rttm")
    print(f"--- {scen} ({len(ref)} segmentos) ---")
    # 1. cópia exata
    measure("copia exata", ref, ref)
    # 2. shift global de 500ms
    shifted = [{"speaker": s["speaker"], "start": s["start"] + 0.5,
                "end": s["end"] + 0.5} for s in ref]
    measure("shift 500ms", ref, shifted)
    # 3. troca de labels (confusão total)
    speakers = sorted({s["speaker"] for s in ref})
    swap = {sp: speakers[(i + 1) % len(speakers)]
            for i, sp in enumerate(speakers)}
    confused = [{"speaker": swap[s["speaker"]], "start": s["start"],
                 "end": s["end"]} for s in ref]
    measure("labels trocados", ref, confused)
    # 4. truncamento 20% do fim
    total_end = max(s["end"] for s in ref)
    cut = total_end * 0.8
    truncated = [s for s in ref if s["end"] <= cut]
    measure("truncado 20%", ref, truncated)
    # 5. merge de tudo num falante só
    merged = [{"speaker": speakers[0], "start": s["start"],
               "end": s["end"]} for s in ref]
    measure("um so falante", ref, merged)
