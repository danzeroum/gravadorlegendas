"""Utilitários de análise de sinal para testes de fidelidade.

Funções puras de medição usadas pelos testes de integridade (FID-*),
pelo golden master (``scripts/fidelity_golden.py``) e pelo gerador de
relatório (``scripts/build_fidelity_report.py``).

Todas as medidas são **propriedades físicas estáveis do sinal**
(frequência de pico, RMS, duração, contagem de frames) — nunca
wall-clock — para que o golden master não apodreça.
"""
from __future__ import annotations

import numpy as np


def rms(x: np.ndarray) -> float:
    """RMS (root-mean-square) do sinal."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


def rms_dbfs(x: np.ndarray) -> float:
    """RMS em dBFS (referência full-scale = 1.0). Silêncio = -inf."""
    r = rms(x)
    if r <= 0.0:
        return float("-inf")
    return float(20.0 * np.log10(r))


def db(x: float, ref: float = 1.0) -> float:
    """Razão em dB entre ``x`` e ``ref``."""
    if x <= 0.0 or ref <= 0.0:
        return float("-inf")
    return float(10.0 * np.log10(x / ref))


def spectral_peak_hz(
    x: np.ndarray,
    sample_rate: int = 16000,
    freq_range: tuple[float, float] = (50.0, 7900.0),
) -> float:
    """Frequência dominante (pico espectral) via FFT com janela Hann.

    Interpolação parabólica do pico para resolução sub-bin — necessária
    para verificar ±5 Hz com senoide de 3 s (resolução de bin ~0.33 Hz
    já seria suficiente; interpolação dá margem extra).
    """
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size < 16:
        raise ValueError("sinal curto demais para análise espectral")
    window = np.hanning(arr.size)
    spectrum = np.abs(np.fft.rfft(arr * window))
    freqs = np.fft.rfftfreq(arr.size, d=1.0 / sample_rate)
    lo, hi = freq_range
    mask = (freqs >= lo) & (freqs <= hi)
    if not mask.any():
        raise ValueError(f"nenhum bin na faixa {freq_range}")
    idx_local = int(np.argmax(spectrum[mask]))
    idx = int(np.nonzero(mask)[0][idx_local])

    # Interpolação parabólica sub-bin (vizinhos do pico)
    if 0 < idx < len(spectrum) - 1:
        a, b, c = spectrum[idx - 1], spectrum[idx], spectrum[idx + 1]
        denom = a - 2.0 * b + c
        delta = 0.0
        if abs(denom) > 1e-30:
            num = 0.5 * (a - c)
            # clamp para estabilidade numérica
            delta = float(np.clip(num / denom, -0.5, 0.5))
        bin_hz = sample_rate / arr.size
        return float(freqs[idx] + delta * bin_hz)
    return float(freqs[idx])


def dc_offset(x: np.ndarray) -> float:
    """Offset DC (média aritmética das amostras)."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


def clipped_fraction(x: np.ndarray, tol: float = 1e-6) -> float:
    """Fração de amostras nos trilhos de saturação (rail hits).

    Um sinal clipado tem fração significativa de amostras exatamente
    iguais ao máximo/mínimo observado. Um sinal saudável tem apenas
    ~1-2 amostras tocando o pico (fração ~0).

    ``tol`` é a tolerância numérica para considerar uma amostra "no
    trilho" (absorve erro de quantização PCM).
    """
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    peak = float(np.max(np.abs(arr)))
    if peak == 0.0:
        return 0.0
    at_rail = np.abs(np.abs(arr) - peak) <= tol
    return float(np.mean(at_rail))


def sample_range(x: np.ndarray) -> tuple[float, float]:
    """Valor mínimo e máximo das amostras."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return (0.0, 0.0)
    return (float(np.min(arr)), float(np.max(arr)))


def snr_db(signal: np.ndarray, noisy: np.ndarray) -> float:
    """SNR em dB entre sinal de referência e sinal degradado.

    SNR = 10*log10(P_sinal / P_erro), onde erro = noisy - signal.
    Requer arrays do mesmo tamanho.
    """
    s = np.asarray(signal, dtype=np.float64).ravel()
    n = np.asarray(noisy, dtype=np.float64).ravel()
    if s.shape != n.shape:
        raise ValueError(f"shapes incompatíveis: {s.shape} vs {n.shape}")
    sig_power = float(np.mean(s * s))
    err = n - s
    err_power = float(np.mean(err * err))
    if err_power == 0.0:
        return float("inf")
    if sig_power == 0.0:
        return float("-inf")
    return float(10.0 * np.log10(sig_power / err_power))


def total_energy(x: np.ndarray) -> float:
    """Energia total (soma dos quadrados)."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    return float(np.sum(arr * arr))


def duration_s(x: np.ndarray, sample_rate: int = 16000) -> float:
    """Duração temporal do sinal em segundos."""
    return float(len(np.asarray(x).ravel())) / float(sample_rate)


def percentile95(values: list[float]) -> float:
    """p95 estável (mesma convenção do LatencyTracker do produto)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * 0.95)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]
