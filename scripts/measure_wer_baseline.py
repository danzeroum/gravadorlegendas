"""Calibra WER/CER real do pipeline STT (espeak-ng TTS -> whisper tiny).

Executa uma vez para fixar thresholds por categoria no manifesto.
Não é teste — é medição de baseline (evidência para o manifesto).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from src.audio.transcribe import WHISPER_DOWNLOAD_ROOT  # noqa: E402
from tests.fixtures import signal_generators as sg  # noqa: E402
from tests.fidelity.text_metrics import cer, wer  # noqa: E402

SR = 16000
REFERENCE = "teste de transcrição local no Fedora"


def tts_phrase(dest: Path, text: str, speed: int = 90) -> np.ndarray:
    cmd = ["espeak-ng", "-v", "pt-br", "-s", str(speed), "-g", "8",
           "-w", str(dest), text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    audio, rate = sf.read(str(dest), dtype="float64")
    if rate != SR:
        audio = sg.resample(audio, rate, SR)
    return np.clip(audio, -1.0, 1.0)


def transcribe(model, sig: np.ndarray) -> str:
    segments, _ = model.transcribe(
        sig.astype(np.float32), language="pt", beam_size=1,
        temperature=0.0, vad_filter=True,
    )
    return " ".join((s.text or "").strip() for s in segments
                    if (s.text or "").strip())


from faster_whisper import WhisperModel  # noqa: E402

model = WhisperModel("base", device="cpu",
                     download_root=str(WHISPER_DOWNLOAD_ROOT))

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)

    # Cenário clean
    clean = tts_phrase(tmp_path / "clean.wav", REFERENCE)
    text_clean = transcribe(model, clean)
    print(f"clean: {text_clean!r}")
    print(f"  WER={wer(REFERENCE, text_clean):.3f} "
          f"CER={cer(REFERENCE, text_clean):.3f}")

    # Cenário moderate_noise (SNR 10 dB)
    noisy = sg.add_noise(clean, snr_db=10.0, seed=99)
    text_noisy = transcribe(model, noisy)
    print(f"moderate_noise (10 dB): {text_noisy!r}")
    print(f"  WER={wer(REFERENCE, text_noisy):.3f} "
          f"CER={cer(REFERENCE, text_noisy):.3f}")

    # Cenário low_volume (amplitude /8)
    low = clean * 0.125
    text_low = transcribe(model, low)
    print(f"low_volume (0.125x): {text_low!r}")
    print(f"  WER={wer(REFERENCE, text_low):.3f} "
          f"CER={cer(REFERENCE, text_low):.3f}")

    # Frase mais longa (stress)
    LONG = ("reuniao de projeto gravada localmente com transcrição "
            "automatica em portugues")
    long_clean = tts_phrase(tmp_path / "long.wav", LONG)
    text_long = transcribe(model, long_clean)
    print(f"long_clean: {text_long!r}")
    print(f"  WER={wer(LONG, text_long):.3f} "
          f"CER={cer(LONG, text_long):.3f}")
