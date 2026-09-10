"""Geradores determinísticos de sinais de áudio para testes de fidelidade.

Todos os geradores são funções puras com **seed explícita** quando há
aleatoriedade envolvida. O mesmo seed + mesma versão de numpy produz os
mesmos arrays (e, após quantização PCM16, os mesmos bytes) em qualquer
plataforma — a aritmética de float64/float32 do numpy é determinística
para as operações usadas aqui (seno, soma, clip, cast).

O corpus versionado é materializado por ``scripts/gen_fidelity_fixtures.py``
a partir destes geradores. Ver ``tests/fixtures/corpus/manifest.yaml``.

Nenhum destes geradores usa chamada externa (espeak, TTS de nuvem, etc):
pseudo-fala é modulação AM/FM de portadora harmônica — reproduzível em
qualquer ambiente com numpy.

Formato canônico do pipeline do produto: PCM s16le mono 16 kHz
(ver ``src/platform.types.AudioChunk``).
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Conversões de formato (float [-1, 1] <-> PCM s16le bytes)
# ---------------------------------------------------------------------------

_S16_SCALE = 32767.0


def float_to_pcm_s16le(x: np.ndarray) -> bytes:
    """Converte array float ([-1, 1]) para bytes PCM s16le mono."""
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"Esperado array 1-D, recebeu shape {arr.shape}")
    arr = np.clip(arr, -1.0, 1.0)
    return (np.rint(arr * _S16_SCALE).astype(np.int16)).tobytes()


def pcm_s16le_to_float(data: bytes, channels: int = 1) -> np.ndarray:
    """Converte bytes PCM s16le para float em [-1, 1].

    ``channels=1`` retorna array 1-D (n,). ``channels=2`` retorna
    array 2-D (n_frames, 2).
    """
    arr = np.frombuffer(data, dtype=np.int16)
    if channels == 1:
        return arr.astype(np.float64) / 32768.0
    if len(arr) % channels != 0:
        raise ValueError(
            f"Tamanho de buffer {len(arr)} não é múltiplo de {channels} canais"
        )
    return arr.astype(np.float64).reshape(-1, channels) / 32768.0


# ---------------------------------------------------------------------------
# Geradores determinísticos (seed explícita quando há aleatoriedade)
# ---------------------------------------------------------------------------

def sine(
    freq_hz: float = 1000.0,
    duration_s: float = 3.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
    phase: float = 0.0,
) -> np.ndarray:
    """Senoide pura — referência de pico espectral e RMS."""
    n = int(round(duration_s * sample_rate))
    t = np.arange(n, dtype=np.float64) / sample_rate
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t + phase)).astype(np.float64)


def silence(duration_s: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    """Silêncio digital exato (zeros)."""
    n = int(round(duration_s * sample_rate))
    return np.zeros(n, dtype=np.float64)


def white_noise(
    duration_s: float = 3.0,
    sample_rate: int = 16000,
    rms_target: float = 0.05,
    seed: int = 42,
) -> np.ndarray:
    """Ruído branco gaussiano com RMS controlado.

    Normalizado para ``rms_target`` exato em float64 — determinístico
    por seed.
    """
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * sample_rate))
    x = rng.standard_normal(n)
    rms = float(np.sqrt(np.mean(x * x)))
    if rms == 0.0:  # pragma: no cover — impossível na prática
        return np.zeros(n)
    return (x * (rms_target / rms)).astype(np.float64)


def speech_like(
    duration_s: float = 4.0,
    sample_rate: int = 16000,
    f0: float = 140.0,
    seed: int = 7,
    amplitude: float = 0.4,
) -> np.ndarray:
    """Sinal pseudo-fala determinístico, sem chamada externa.

    Técnica: portadora de harmônicos de ``f0`` (queda 1/n até o limite de
    Nyquist), modulada em amplitude por um envelope de sílabas (~4 Hz),
    com pausas entre "palavras" e jitter de frequência lento — tudo derivado
    de ``np.random.default_rng(seed)``.

    IMPORTANTE: este sinal é **pseudo-fala** — valida pipeline, métricas,
    timeline e sincronismo. NÃO é representativo de WER/DER em vozes
    humanas (documentado em docs/qualidade-audio/DECISOES.md D-003).
    """
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * sample_rate))
    t = np.arange(n, dtype=np.float64) / sample_rate

    # Jitter lento de frequência (vibrato determinístico)
    vibrato = 0.02 * np.sin(2.0 * np.pi * 1.3 * t + rng.uniform(0, 2 * np.pi))
    inst_f0 = f0 * (1.0 + vibrato)

    # Portadora: soma de harmônicos com queda 1/n
    carrier = np.zeros(n, dtype=np.float64)
    k = 1
    while k * f0 < sample_rate / 2.0:
        carrier += np.sin(2.0 * np.pi * np.cumsum(inst_f0) / sample_rate * k) / k
        k += 1
    carrier /= max(k - 1, 1)

    # Envelope de sílabas: modulação AM ~4 Hz
    syllable_rate = 4.0
    phase = 2.0 * np.pi * syllable_rate * t + rng.uniform(0, 2 * np.pi)
    syllable_env = 0.5 * (1.0 + np.sin(phase))
    syllable_env = syllable_env ** 1.5  # acentua vales (pausas curtas)

    # Pausas entre "palavras": máscara determinística de gaps (~120 ms a cada
    # ~0.8 s, com jitter de posição derivado do rng)
    word_mask = np.ones(n, dtype=np.float64)
    gap_samples = int(0.12 * sample_rate)
    pos = int(rng.uniform(0.3, 0.6) * sample_rate)
    while pos + gap_samples < n:
        word_mask[pos: pos + gap_samples] = 0.0
        pos += int((0.8 + rng.uniform(-0.1, 0.1)) * sample_rate)

    x = carrier * syllable_env * word_mask

    # Normalização para amplitude de pico alvo
    peak = float(np.max(np.abs(x)))
    if peak > 0:
        x = x * (amplitude / peak)
    return x.astype(np.float64)


def mix_speakers(
    timeline: list[tuple[int, float, float]],
    duration_s: float | None = None,
    sample_rate: int = 16000,
    seeds: list[int] | None = None,
    f0s: list[float] | None = None,
) -> np.ndarray:
    """Mix de 2-3 pseudo-falantes com timeline conhecida.

    Args:
        timeline: Lista de ``(speaker_idx, start_s, end_s)`` — permite
            alternância, sobreposição e entrada/saída de falante.
        duration_s: Duração total (None = fim do último segmento + 0.2 s).
        seeds: Seeds por falante (default [101, 202, 303]).
        f0s: f0 por falante (default [110, 180, 240] Hz — vozes graves,
            médias e agudas para separabilidade espectral).

    Returns:
        Soma dos pseudo-falantes clipada em [-1, 1].
    """
    if seeds is None:
        seeds = [101, 202, 303]
    if f0s is None:
        f0s = [110.0, 180.0, 240.0]
    max_spk = max(s for s, _, _ in timeline)
    if max_spk >= len(f0s):
        raise ValueError(f"speaker_idx {max_spk} sem f0 configurado")

    if duration_s is None:
        duration_s = max(e for _, _, e in timeline) + 0.2

    out = np.zeros(int(round(duration_s * sample_rate)), dtype=np.float64)
    for spk, start, end in timeline:
        seg_dur = end - start
        if seg_dur <= 0:
            continue
        seg = speech_like(
            duration_s=seg_dur,
            sample_rate=sample_rate,
            f0=f0s[spk],
            seed=seeds[spk],
            amplitude=0.35,
        )
        i0 = int(round(start * sample_rate))
        i1 = min(i0 + len(seg), len(out))
        out[i0:i1] += seg[: i1 - i0]
    return np.clip(out, -1.0, 1.0).astype(np.float64)


def timeline_to_rttm(
    timeline: list[tuple[int, float, float]],
    uri: str = "corpus",
) -> str:
    """Converte timeline ``(speaker, start, end)`` em texto RTTM padrão.

    Formato RTTM (NIST): ``SPEAKER <uri> <channel> <start> <dur>
    <NA> <NA> <speaker> <NA> <NA>``.
    """
    lines = []
    for spk, start, end in sorted(timeline, key=lambda s: (s[1], s[0])):
        dur = round(end - start, 3)
        lines.append(
            f"SPEAKER {uri} 1 {start:.3f} {dur:.3f} "
            f"<NA> <NA> SPEAKER_{spk:02d} <NA> <NA>"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Degradações determinísticas
# ---------------------------------------------------------------------------

def apply_clipping(x: np.ndarray, clip_level: float = 0.5) -> np.ndarray:
    """Clipping duro: satura em ±``clip_level``.

    ``clip_level`` menor que o pico do sinal produz distorção mensurável
    (o % de amostras saturadas é verificável por análise).
    """
    return np.clip(np.asarray(x, dtype=np.float64), -clip_level, clip_level)


def apply_dropout(
    x: np.ndarray,
    gaps: list[tuple[float, float]],
    sample_rate: int = 16000,
) -> np.ndarray:
    """Zera intervalos ``(start_s, end_s)`` — dropouts/gaps de captura."""
    out = np.array(x, dtype=np.float64, copy=True)
    for start, end in gaps:
        i0 = int(round(start * sample_rate))
        i1 = int(round(end * sample_rate))
        out[i0:i1] = 0.0
    return out


def resample(
    x: np.ndarray,
    orig_rate: int,
    target_rate: int,
) -> np.ndarray:
    """Reamostragem determinística preservando duração temporal.

    Usa ``scipy.signal.resample_poly`` (filtro FIR anti-aliasing) —
    determinístico entre plataformas para as mesmas versões de scipy.
    """
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(int(orig_rate), int(target_rate))
    up = int(target_rate) // g
    down = int(orig_rate) // g
    return resample_poly(np.asarray(x, dtype=np.float64), up, down).astype(np.float64)


def to_stereo(x: np.ndarray, mode: str = "duplicated") -> np.ndarray:
    """Converte mono para estéreo (shape (n, 2)) com energia controlada.

    Modos:
        - ``duplicated``: ambos canais = x (energia do downmix preservada).
        - ``half``: cada canal = x/√2 (energia total preservada).
        - ``antiphase``: L = x, R = -x (downmix anula — caso adversário).
    """
    x = np.asarray(x, dtype=np.float64)
    if mode == "duplicated":
        return np.stack([x, x], axis=1)
    if mode == "half":
        h = x / np.sqrt(2.0)
        return np.stack([h, h], axis=1)
    if mode == "antiphase":
        return np.stack([x, -x], axis=1)
    raise ValueError(f"modo desconhecido: {mode!r}")


def downmix_mono(stereo: np.ndarray) -> np.ndarray:
    """Downmix estéreo -> mono por média aritmética dos canais."""
    arr = np.asarray(stereo, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError(f"Esperado array 2-D (n, >=2), recebeu {arr.shape}")
    return arr.mean(axis=1)


def add_noise(
    signal: np.ndarray,
    snr_db: float,
    seed: int = 99,
) -> np.ndarray:
    """Mistura ruído branco gaussiano no SNR alvo (determinístico por seed).

    SNR = 10*log10(P_sinal / P_ruído). Clipa resultado em [-1, 1].
    """
    rng = np.random.default_rng(seed)
    x = np.asarray(signal, dtype=np.float64)
    sig_power = float(np.mean(x * x))
    if sig_power == 0:
        raise ValueError("add_noise exige sinal com potência não-nula")
    noise_power = sig_power / (10.0 ** (snr_db / 10.0))
    noise = rng.standard_normal(len(x)) * np.sqrt(noise_power)
    return np.clip(x + noise, -1.0, 1.0).astype(np.float64)


def add_dc_offset(x: np.ndarray, offset: float) -> np.ndarray:
    """Adiciona DC offset (caso adversário para FID-06)."""
    return (np.asarray(x, dtype=np.float64) + offset).astype(np.float64)
