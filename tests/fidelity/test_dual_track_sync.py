"""SYNC-01..SYNC-03 — Sincronismo e robustez do DualTrackRecorder.

Classificação honesta: integração com código real (offline). O
``DualTrackRecorder`` real roda de ponta a ponto (escrita WAV via módulo
``wave``, timestamps de primeiro frame); os chunks vêm de geradores
determinísticos e o relógio é um ``FakeClock`` injetado via patch do
módulo — determinismo total, sem sleeps arbitrários.

Budgets calibrados (manifesto do corpus, seção ``budgets.dual_track``):
medidos com baseline local antes de serem fixados (ver DECISOES.md).
"""
from __future__ import annotations

import wave
from unittest.mock import patch

import numpy as np
import pytest

from src.audio.recorder import DualTrackRecorder
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
CHUNK_FRAMES = 480
CHUNK_BYTES = CHUNK_FRAMES * 2


class FakeClock:
    """Relógio monotônico controlável — determinismo sem sleeps."""

    def __init__(self, t0: float = 1000.0) -> None:
        self._now = float(t0)

    def monotonic(self) -> float:
        return self._now

    def advance(self, dt: float) -> None:
        self._now += dt


def _mic_chunk(i: int) -> bytes:
    """Chunk PCM determinístico do trilho mic (senoide 440 Hz)."""
    sig = sg.sine(freq_hz=440.0, duration_s=CHUNK_FRAMES / SR,
                  sample_rate=SR, amplitude=0.3, phase=i * 0.1)
    return sg.float_to_pcm_s16le(sig)


def _sys_chunk(i: int) -> bytes:
    """Chunk PCM determinístico do trilho sistema (senoide 1 kHz)."""
    sig = sg.sine(freq_hz=1000.0, duration_s=CHUNK_FRAMES / SR,
                  sample_rate=SR, amplitude=0.3, phase=i * 0.1)
    return sg.float_to_pcm_s16le(sig)


# ---------------------------------------------------------------------------
# SYNC-01 — Drift entre trilhas em cenário controlado
# ---------------------------------------------------------------------------

class TestSync01Drift:
    def test_first_frame_drift_measures_simulated_offset(
        self, corpus_manifest, tmp_path
    ):
        """Offset simulado de 0.25 s no início do sistema é medido com erro
        < 0.005 s (budget do manifesto) pelo recorder real.

        Cenário controlado: mic começa a falar em t=1000.0; sistema só em
        t=1000.25 (device lento para abrir). O drift reportado deve ser
        exatamente o offset simulado.
        """
        budgets = corpus_manifest["budgets"]["dual_track"]
        clock = FakeClock(t0=1000.0)
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR)
        with patch("src.audio.recorder.time", new=clock):
            recorder.start()
            recorder.feed_mic(_mic_chunk(0))       # t=1000.0
            clock.advance(0.25)
            recorder.feed_system(_sys_chunk(0))    # t=1000.25
            for i in range(1, 50):
                recorder.feed_mic(_mic_chunk(i))
                recorder.feed_system(_sys_chunk(i))
            result = recorder.stop()

        assert result.mic_start_monotonic is not None
        assert result.system_start_monotonic is not None
        drift = result.system_start_monotonic - result.mic_start_monotonic
        assert abs(drift - 0.25) <= budgets["first_frame_drift_error_s"], (
            f"drift medido {drift:.4f} s diverge do offset simulado 0.25 s"
        )

    def test_equal_feed_zero_sample_drift(self, corpus_manifest, tmp_path):
        """Trilhas alimentadas igualmente: drift de samples = 0 exato."""
        budgets = corpus_manifest["budgets"]["dual_track"]
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR)
        recorder.start()
        for i in range(120):
            recorder.feed_mic(_mic_chunk(i))
            recorder.feed_system(_sys_chunk(i))
        result = recorder.stop()
        assert result.mic_samples == result.system_samples
        sample_drift_s = abs(result.mic_samples - result.system_samples) / SR
        assert sample_drift_s <= budgets["equal_feed_sample_drift_s"]

    def test_unequal_feed_measures_exact_sample_gap(self, tmp_path):
        """Gap de 2 chunks entre trilhas é medido exatamente (2×30 ms)."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR)
        recorder.start()
        for i in range(100):
            recorder.feed_mic(_mic_chunk(i))
        for i in range(98):
            recorder.feed_system(_sys_chunk(i))
        result = recorder.stop()
        gap_samples = result.mic_samples - result.system_samples
        assert gap_samples == 2 * CHUNK_FRAMES
        gap_s = gap_samples / SR
        assert abs(gap_s - 0.06) < 1e-9  # 2 chunks de 30 ms


# ---------------------------------------------------------------------------
# SYNC-02 — Igualdade de duração/frames dentro de tolerância
# ---------------------------------------------------------------------------

class TestSync02DurationEquality:
    def test_duration_matches_sample_count(self, corpus_manifest, tmp_path):
        """duration_s == max(samples)/rate dentro da tolerância do budget."""
        budgets = corpus_manifest["budgets"]["dual_track"]
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR)
        recorder.start()
        n = 150
        for i in range(n):
            recorder.feed_mic(_mic_chunk(i))
            recorder.feed_system(_sys_chunk(i))
        result = recorder.stop()
        expected_duration = n * CHUNK_FRAMES / SR
        assert abs(result.duration_s - expected_duration) <= budgets[
            "duration_tolerance_s"
        ]
        assert result.mic_samples == n * CHUNK_FRAMES
        assert result.system_samples == n * CHUNK_FRAMES

    def test_duration_uses_longest_track(self, tmp_path):
        """Trilhas de tamanhos distintos: duração = trilha mais longa."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR)
        recorder.start()
        for i in range(100):
            recorder.feed_mic(_mic_chunk(i))
        for i in range(60):
            recorder.feed_system(_sys_chunk(i))
        result = recorder.stop()
        assert result.duration_s == pytest.approx(100 * CHUNK_FRAMES / SR)

    def test_result_metadata_consistent(self, tmp_path):
        """Metadados do resultado: rate/channels/samples coerentes."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path), sample_rate=SR,
                                     channels=1)
        recorder.start()
        for i in range(10):
            recorder.feed_mic(_mic_chunk(i))
        result = recorder.stop()
        assert result.sample_rate == SR
        assert result.channels == 1
        assert result.mic_samples == 10 * CHUNK_FRAMES
        assert result.mic_path is not None and result.system_path is not None


# ---------------------------------------------------------------------------
# SYNC-03 — stop() no meio do stream produz WAVs válidos e recuperáveis
# ---------------------------------------------------------------------------

class TestSync03MidStreamStop:
    def _read_wav(self, path: str) -> tuple:
        with wave.open(path, "rb") as wf:
            params = (
                wf.getnchannels(), wf.getsampwidth(), wf.getframerate(),
                wf.getnframes(),
            )
            frames = wf.readframes(wf.getnframes())
        return params, frames

    def test_stop_mid_stream_yields_valid_wavs(self, tmp_path):
        """Parar após N chunks e meio: WAVs válidos, headers corretos,
        samples byte-exatos com o que foi efetivamente alimentado."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path),
                                     sample_rate=SR)
        recorder.start()
        fed = [(_mic_chunk(i), _sys_chunk(i)) for i in range(73)]
        for mic, sysc in fed:
            recorder.feed_mic(mic)
            recorder.feed_system(sysc)
        result = recorder.stop(timeout_s=2.0)

        for path, samples in ((result.mic_path, result.mic_samples),
                              (result.system_path, result.system_samples)):
            (nch, width, rate, nframes), frames = self._read_wav(path)
            assert nch == 1
            assert width == 2  # s16le
            assert rate == SR
            assert nframes == samples == 73 * CHUNK_FRAMES
            assert len(frames) == samples * 2

    def test_feed_after_stop_is_ignored(self, tmp_path):
        """Chunks após stop() não corrompem os arquivos fechados."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path),
                                     sample_rate=SR)
        recorder.start()
        for i in range(10):
            recorder.feed_mic(_mic_chunk(i))
        result = recorder.stop()
        samples_at_stop = result.mic_samples
        # feed tardio — deve ser ignorado silenciosamente (is_running False)
        recorder.feed_mic(_mic_chunk(999))
        recorder.feed_system(_sys_chunk(999))
        _, frames = self._read_wav(result.mic_path)
        assert len(frames) // 2 == samples_at_stop

    def test_partial_and_odd_chunks_do_not_corrupt_wav(self, tmp_path):
        """Chunk ímpar (sample incompleto) no meio do stream: WAV final
        continua válido — degradação graciosa documentada."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path),
                                     sample_rate=SR)
        recorder.start()
        for i in range(20):
            recorder.feed_mic(_mic_chunk(i))
        recorder.feed_mic(_mic_chunk(20)[:-1])  # 959 bytes (ímpar)
        for i in range(5):
            recorder.feed_mic(_mic_chunk(21 + i))
        recorder.feed_system(_sys_chunk(0))
        result = recorder.stop()
        (nch, width, rate, nframes), frames = self._read_wav(result.mic_path)
        assert nch == 1 and width == 2 and rate == SR
        # Writer conta samples com // (2*channels): 959 bytes -> 479 samples
        assert nframes == 25 * CHUNK_FRAMES + 479
        assert len(frames) % 2 == 0

    def test_empty_tracks_produce_valid_empty_wavs(self, tmp_path):
        """Nenhum chunk alimentado: WAVs válidos com 0 frames."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path),
                                     sample_rate=SR)
        recorder.start()
        result = recorder.stop()
        for path in (result.mic_path, result.system_path):
            (nch, width, rate, nframes), frames = self._read_wav(path)
            assert (nch, width, rate, nframes) == (1, 2, SR, 0)
            assert frames == b""

    def test_wav_content_is_byte_exact(self, tmp_path):
        """Conteúdo gravado == bytes alimentados (sem re-codificação)."""
        recorder = DualTrackRecorder(output_dir=str(tmp_path),
                                     sample_rate=SR)
        recorder.start()
        mic_data = [_mic_chunk(i) for i in range(30)]
        for c in mic_data:
            recorder.feed_mic(c)
        result = recorder.stop()
        _, frames = self._read_wav(result.mic_path)
        assert frames == b"".join(mic_data), (
            "WAV diverge do PCM alimentado — perda/corrupção no gravador"
        )
