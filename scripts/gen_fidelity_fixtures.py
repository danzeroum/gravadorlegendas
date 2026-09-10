#!/usr/bin/env python3
"""Gera o corpus determinístico de fidelidade de áudio.

Uso:
    python scripts/gen_fidelity_fixtures.py            # gera corpus + manifestos
    python scripts/gen_fidelity_fixtures.py --check    # verifica regenerabilidade

Materializa em ``tests/fixtures/corpus/``:
    - ``audio/*.wav`` — fixtures PCM s16le mono 16 kHz (pequenos: 2–6 s);
    - ``rttm/*.rttm`` — referências de diarização para cenários multi-falante;
    - ``manifest.yaml`` — manifesto com seed, duração, limiares e origem.

Determinismo: mesmo seed + mesmas versões de numpy/scipy/soundfile ⇒
mesmos bytes de áudio. Os WAVs são escritos com cabeçalho padrão RIFF
(sem timestamp). O manifesto registra o sha256 de cada fixture para
verificação de integridade (usado também pelo golden master).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures import signal_generators as sg  # noqa: E402

CORPUS_DIR = ROOT / "tests" / "fixtures" / "corpus"
AUDIO_DIR = CORPUS_DIR / "audio"
RTTM_DIR = CORPUS_DIR / "rttm"
SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# Definição declarativa dos cenários (única fonte de verdade do corpus)
# ---------------------------------------------------------------------------

# Timelines multi-falante (speaker, start_s, end_s)
TL_TWO_ALT = [
    (0, 0.0, 2.0),
    (1, 2.2, 4.2),
    (0, 4.4, 6.0),
]
TL_TWO_OVERLAP = [
    (0, 0.0, 2.5),
    (1, 2.0, 4.5),   # overlap 0.5 s com falante 0
    (0, 4.3, 5.0),   # overlap 0.2 s com falante 1
]
TL_THREE = [
    (0, 0.0, 1.5),
    (1, 1.7, 3.0),
    (2, 3.2, 4.5),
    (0, 4.7, 6.0),
    (1, 6.1, 7.0),
    (2, 7.2, 8.0),
]
TL_ENTER_EXIT = [
    (0, 0.0, 2.0),
    (1, 1.8, 3.8),   # falante 1 entra com overlap curto
    (0, 4.0, 4.6),   # falante 0 sai logo depois
    (1, 4.8, 6.0),   # falante 1 continua sozinho
]


def _build_signals() -> dict[str, dict]:
    """Constrói todos os sinais do corpus (determinístico)."""
    scenarios: dict[str, dict] = {}

    # -- Referências físicas -------------------------------------------
    sine_1k = sg.sine(freq_hz=1000.0, duration_s=3.0, sample_rate=SAMPLE_RATE,
                      amplitude=0.5)
    scenarios["sine_1k"] = {
        "signal": sine_1k,
        "seed": None,
        "description": "Senoide pura de 1 kHz, amplitude 0.5 — referência "
                       "de pico espectral (FID-01) e RMS (FID-02).",
        "thresholds": {"spectral_peak_hz_tol": 5.0, "rms_db_tol": 1.0},
    }

    # -- Voz/sinal limpo -------------------------------------------------
    clean = sg.speech_like(duration_s=5.0, sample_rate=SAMPLE_RATE,
                           f0=140.0, seed=7, amplitude=0.4)
    scenarios["clean_speech_like"] = {
        "signal": clean,
        "seed": 7,
        "description": "Pseudo-fala limpa de 1 falante (f0=140 Hz, envelope "
                       "de sílabas 4 Hz). Cenário base de fidelidade.",
        "thresholds": {"spectral_peak_hz_tol": 40.0},
        "transcription": None,
    }

    # -- Ruído moderado ---------------------------------------------------
    noisy = sg.add_noise(clean, snr_db=10.0, seed=99)
    scenarios["moderate_noise"] = {
        "signal": noisy,
        "seed": 7,
        "noise_seed": 99,
        "description": "Pseudo-fala + ruído branco gaussiano com SNR alvo "
                       "de 10 dB — cenário de ruído moderado.",
        "thresholds": {"snr_target_db": 10.0, "snr_tolerance_db": 1.5},
    }

    # -- 2 falantes alternados ------------------------------------------
    scenarios["two_speakers_no_overlap"] = {
        "signal": sg.mix_speakers(TL_TWO_ALT, duration_s=6.2,
                                  sample_rate=SAMPLE_RATE),
        "seed": 101,
        "description": "Dois pseudo-falantes alternados (110/180 Hz) sem "
                       "sobreposição, com timeline conhecida e RTTM.",
        "timeline": TL_TWO_ALT,
        "rttm": "rttm/two_speakers_no_overlap.rttm",
        "thresholds": {"der_exact_copy": 0.0, "der_time_shift_500ms_max": 0.12},
    }

    # -- 2 falantes com overlap ------------------------------------------
    scenarios["two_speakers_overlap"] = {
        "signal": sg.mix_speakers(TL_TWO_OVERLAP, duration_s=5.2,
                                  sample_rate=SAMPLE_RATE),
        "seed": 202,
        "description": "Dois pseudo-falantes com sobreposição deliberada "
                       "(0.5 s + 0.2 s) — caso adversário de diarização.",
        "timeline": TL_TWO_OVERLAP,
        "rttm": "rttm/two_speakers_overlap.rttm",
        "thresholds": {"der_exact_copy": 0.0},
    }

    # -- 3 falantes --------------------------------------------------------
    scenarios["three_speakers"] = {
        "signal": sg.mix_speakers(TL_THREE, duration_s=8.2,
                                  sample_rate=SAMPLE_RATE),
        "seed": 303,
        "description": "Três pseudo-falantes alternados (110/180/240 Hz) "
                       "com timeline conhecida.",
        "timeline": TL_THREE,
        "rttm": "rttm/three_speakers.rttm",
        "thresholds": {"der_exact_copy": 0.0},
    }

    # -- Entrada/saída de falante -----------------------------------------
    scenarios["speaker_enter_exit"] = {
        "signal": sg.mix_speakers(TL_ENTER_EXIT, duration_s=6.2,
                                  sample_rate=SAMPLE_RATE),
        "seed": 404,
        "description": "Falante 1 entra no meio da fala do falante 0; "
                       "falante 0 sai e o 1 continua — entra/sai de falante.",
        "timeline": TL_ENTER_EXIT,
        "rttm": "rttm/speaker_enter_exit.rttm",
        "thresholds": {"der_exact_copy": 0.0},
    }

    # -- Clipping ----------------------------------------------------------
    clipped = sg.apply_clipping(clean, clip_level=0.25)
    scenarios["clipped"] = {
        "signal": clipped,
        "seed": 7,
        "description": "Pseudo-fala clipada em ±0.25 (pico original 0.4) — "
                       "distorção mensurável por fração de amostras saturadas.",
        "thresholds": {"clipped_fraction_min": 0.02},
    }

    # -- Dropout -----------------------------------------------------------
    dropout = sg.apply_dropout(
        clean,
        gaps=[(1.0, 1.4), (2.6, 3.3), (4.2, 4.5)],
        sample_rate=SAMPLE_RATE,
    )
    scenarios["dropout"] = {
        "signal": dropout,
        "seed": 7,
        "description": "Pseudo-fala com 3 gaps (400/700/300 ms) — perda de "
                       "dados de captura mensurável.",
        "thresholds": {"silent_gap_count": 3},
    }

    # -- Silêncio ------------------------------------------------------------
    scenarios["silence"] = {
        "signal": sg.silence(duration_s=2.0, sample_rate=SAMPLE_RATE),
        "seed": None,
        "description": "Silêncio digital exato — baseline de RMS -inf e "
                       "sem pico espectral.",
        "thresholds": {"rms_max": 0.0},
    }

    return scenarios


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def write_corpus(force: bool = False) -> Path:
    """Materializa o corpus em disco. Retorna o caminho do manifesto."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RTTM_DIR.mkdir(parents=True, exist_ok=True)

    scenarios = _build_signals()
    entries = []

    for scen_id, spec in scenarios.items():
        wav_path = AUDIO_DIR / f"{scen_id}.wav"
        pcm = sg.float_to_pcm_s16le(spec["signal"])
        sf.write(
            str(wav_path),
            np.frombuffer(pcm, dtype=np.int16),
            SAMPLE_RATE,
            subtype="PCM_16",
        )

        entry: dict = {
            "id": scen_id,
            "description": spec["description"],
            "path": f"audio/{scen_id}.wav",
            "seed": spec.get("seed"),
            "format": "wav/pcm_s16le",
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "duration_s": round(len(spec["signal"]) / SAMPLE_RATE, 3),
            "sha256": _sha256_file(wav_path),
            "thresholds": spec.get("thresholds", {}),
            "license": "synthetic-generated",
            "origin": "scripts/gen_fidelity_fixtures.py + "
                      "tests/fixtures/signal_generators.py (determinístico)",
        }
        if spec.get("transcription") is not None:
            entry["transcription"] = spec["transcription"]
        else:
            entry["transcription"] = None
        if "rttm" in spec:
            rttm_path = CORPUS_DIR / spec["rttm"]
            rttm_path.parent.mkdir(parents=True, exist_ok=True)
            rttm_path.write_text(
                sg.timeline_to_rttm(spec["timeline"], uri=scen_id),
                encoding="utf-8",
            )
            entry["rttm"] = spec["rttm"]
        if "timeline" in spec:
            entry["speakers"] = sorted({s for s, _, _ in spec["timeline"]})
            entry["timeline"] = [
                {"speaker": int(s), "start": round(a, 3), "end": round(b, 3)}
                for s, a, b in spec["timeline"]
            ]
        if "noise_seed" in spec:
            entry["noise_seed"] = spec["noise_seed"]

        entries.append(entry)

    manifest = {
        "schema": "gravadorlegendas/corpus@1",
        "generator": "tests/fixtures/signal_generators.py",
        "generator_version": 1,
        "regenerate": "python scripts/gen_fidelity_fixtures.py",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "canonical_format": "pcm_s16le",
        "privacy": (
            "Todos os fixtures são sintéticos, gerados por código com seed "
            "explícita. Sem voz pessoal, reunião real ou dado confidencial."
        ),
        "wer_policy": {
            "note": (
                "Pseudo-fala sintética NÃO é representativa de WER humano. "
                "Limiares de WER por categoria abaixo aplicam-se a testes de "
                "regressão da infraestrutura de métrica e a testes opt-in "
                "com modelo real sobre áudio TTS determinístico (espeak-ng)."
            ),
            "categories": {
                "clean": {"wer_max": 0.25, "cer_max": 0.15},
                "moderate_noise": {"wer_max": 0.45, "cer_max": 0.30},
                "low_volume": {"wer_max": 0.45, "cer_max": 0.30},
            },
        },
        "der_policy": {
            "collar_s": 0.0,
            "overlap_policy": "padrão pyannote.metrics (overlap conta como "
                              "erro de confusão para hipótese com rótulo único)",
            "note": (
                "DER sobre pseudo-fala valida harness/métrica/contrato — "
                "não qualidade de embeddings em vozes humanas."
            ),
        },
        "scenarios": entries,
    }

    manifest_path = CORPUS_DIR / "manifest.yaml"
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            manifest, f, allow_unicode=True, sort_keys=False, width=100
        )
    return manifest_path


def check_corpus() -> int:
    """Verifica que o corpus em disco bate com a geração do zero.

    Retorna 0 se regenerável (bytes idênticos), 1 caso contrário.
    """
    import tempfile

    scenarios = _build_signals()
    mismatch = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for scen_id, spec in scenarios.items():
            ref_path = AUDIO_DIR / f"{scen_id}.wav"
            if not ref_path.exists():
                print(f"MISSING: {ref_path}")
                mismatch += 1
                continue
            tmp_wav = tmp_path / f"{scen_id}.wav"
            pcm = sg.float_to_pcm_s16le(spec["signal"])
            sf.write(
                str(tmp_wav),
                np.frombuffer(pcm, dtype=np.int16),
                SAMPLE_RATE,
                subtype="PCM_16",
            )
            ref_hash = _sha256_file(ref_path)
            tmp_hash = _sha256_file(tmp_wav)
            if ref_hash != tmp_hash:
                print(f"DRIFT: {scen_id} ({ref_hash[:12]} != {tmp_hash[:12]})")
                mismatch += 1
            else:
                print(f"OK: {scen_id}")
    if mismatch:
        print(f"\n{mismatch} fixture(s) divergem — regenere com "
              f"python scripts/gen_fidelity_fixtures.py")
        return 1
    print("\nCorpus determinístico: 100% regenerável.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="verifica que o corpus versionado é regenerável byte a byte",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(check_corpus())

    manifest_path = write_corpus()
    n_wav = len(list(AUDIO_DIR.glob("*.wav")))
    n_rttm = len(list(RTTM_DIR.glob("*.rttm")))
    total_kb = sum(f.stat().st_size for f in AUDIO_DIR.glob("*.wav")) / 1024
    print(f"Gerados {n_wav} WAVs ({total_kb:.0f} KB) e {n_rttm} RTTMs.")
    print(f"Manifesto: {manifest_path}")


if __name__ == "__main__":
    main()
