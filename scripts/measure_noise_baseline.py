"""Mede baseline local do filtro de ruído (fallback espectral) para
calibrar budgets do teste RUIDO-01 (executa uma vez, não é teste)."""
import sys

sys.path.insert(0, ".")

import numpy as np  # noqa: E402

from src.filter.noise_suppression import RNNoiseFilter  # noqa: E402
from tests.fidelity import dsp_utils as dsp  # noqa: E402
from tests.fixtures import signal_generators as sg  # noqa: E402

SR = 16000
CHUNK = 480

clean = sg.speech_like(duration_s=5.0, sample_rate=SR, seed=7, amplitude=0.4)
noisy = sg.add_noise(clean, snr_db=10.0, seed=99)

filt = RNNoiseFilter(sample_rate=SR)
print("backend:", filt.backend_name)


def run_filter(sig):
    pcm = sg.float_to_pcm_s16le(sig)
    out = bytearray()
    for i in range(0, len(pcm), CHUNK * 2):
        frame = pcm[i: i + CHUNK * 2]
        out.extend(filt.process_frame(frame))
    return sg.pcm_s16le_to_float(bytes(out))


snr_in = dsp.snr_db(clean, noisy)
out_noisy = run_filter(noisy)
snr_out = dsp.snr_db(clean, out_noisy)
print(f"SNR entrada: {snr_in:.2f} dB | SNR saida: {snr_out:.2f} dB | "
      f"ganho: {snr_out - snr_in:+.2f} dB")

# Degradação em sinal limpo
out_clean = run_filter(clean)
snr_clean = dsp.snr_db(clean, out_clean)
print(f"Sinal limpo: SNR(clean vs filtrado) = {snr_clean:.2f} dB")

# Silêncio puro (noise gate)
sil = sg.silence(duration_s=1.0, sample_rate=SR)
out_sil = run_filter(sil)
print(f"Silencio: RMS saida = {dsp.rms(out_sil):.6f} "
      f"(entrada 0.0, gate deveria manter ~0)")

# Ruído puro (sem fala) — gate deveria atenuar
noise_only = sg.white_noise(duration_s=3.0, sample_rate=SR, rms_target=0.01,
                            seed=5)
out_noise = run_filter(noise_only)
print(f"Ruido puro: RMS {dsp.rms(noise_only):.4f} -> {dsp.rms(out_noise):.4f} "
      f"({20 * np.log10(dsp.rms(out_noise) / max(dsp.rms(noise_only), 1e-12)):+.1f} dB)")

# Frame size invariância (T5.4 do produto)
print("frame size igual:", len(run_filter(noisy)) == len(noisy))
