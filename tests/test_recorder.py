"""Testes unitários para DualTrackRecorder (Frente A).

Validam a lógica de gravação dual-track sem depender de PipeWire
real — usam arquivos temporários e chunks sintéticos de PCM s16le.

Os testes de integração T3.1–T3.4 (com sink virtual PipeWire real)
estão em ``tests/integration/test_dual_track_recording_real.py`` e
fazem skip automático em ambientes sem PipeWire/pactl.
"""
from __future__ import annotations

import os
import struct
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from src.audio.recorder import DualTrackRecorder, DualTrackResult, _TrackWriter


def _gen_pcm_sine(freq: float = 440.0, duration_s: float = 0.1,
                  sample_rate: int = 16000, amplitude: float = 0.5) -> bytes:
    """Gera chunk PCM s16le de uma senoide."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    samples = (amplitude * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()


def _gen_pcm_silence(duration_s: float = 0.1, sample_rate: int = 16000) -> bytes:
    """Gera chunk PCM s16le de silêncio puro."""
    n = int(duration_s * sample_rate)
    return (np.zeros(n, dtype=np.int16)).tobytes()


class TestTrackWriter:
    """Testes do writer individual de trilho."""

    def test_open_creates_file_with_wav_header(self, tmp_path):
        path = str(tmp_path / "track.wav")
        w = _TrackWriter(path, sample_rate=16000, channels=1)
        w.open()
        # wave module só escreve o cabeçalho após writeframes() ou close()
        w.write(_gen_pcm_sine(duration_s=0.01))
        w.close()
        assert os.path.exists(path)
        # Arquivo WAV tem pelo menos o cabeçalho (44 bytes) + frames
        assert os.path.getsize(path) >= 44

    def test_write_increments_samples(self, tmp_path):
        path = str(tmp_path / "track.wav")
        w = _TrackWriter(path, sample_rate=16000, channels=1)
        w.open()
        chunk = _gen_pcm_sine(duration_s=0.1)  # 1600 amostras
        w.write(chunk)
        assert w.samples_written == 1600
        w.close()

    def test_first_frame_monotonic_set_on_first_write(self, tmp_path):
        path = str(tmp_path / "track.wav")
        w = _TrackWriter(path, sample_rate=16000, channels=1)
        w.open()
        assert w.first_frame_monotonic is None
        w.write(_gen_pcm_sine(duration_s=0.05))
        assert w.first_frame_monotonic is not None
        w.close()

    def test_close_idempotent(self, tmp_path):
        path = str(tmp_path / "track.wav")
        w = _TrackWriter(path, sample_rate=16000, channels=1)
        w.open()
        w.write(_gen_pcm_sine(duration_s=0.05))
        w.close()
        # Segundo close não deve lançar exceção
        w.close()
        # E nem corromper o arquivo
        with wave.open(path, "rb") as wf:
            assert wf.getnframes() > 0

    def test_write_empty_chunk_is_noop(self, tmp_path):
        path = str(tmp_path / "track.wav")
        w = _TrackWriter(path, sample_rate=16000, channels=1)
        w.open()
        w.write(b"")
        assert w.samples_written == 0
        w.close()


class TestDualTrackRecorderLifecycle:
    """Testes do ciclo start/feed/stop do DualTrackRecorder."""

    def test_start_creates_two_wav_files(self, tmp_path):
        rec = DualTrackRecorder(
            output_dir=str(tmp_path),
            sample_rate=16000,
            prefix="test",
        )
        rec.start()
        # Arquivos não existem ainda (só abertos para escrita, header WAV)
        assert rec.mic_path is not None
        assert rec.system_path is not None
        assert rec.mic_path.endswith("_mic.wav")
        assert rec.system_path.endswith("_sistema.wav")
        assert rec.is_running
        # Feed alguns chunks
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        rec.feed_system(_gen_pcm_sine(freq=880, duration_s=0.1))
        result = rec.stop()
        assert os.path.exists(result.mic_path)
        assert os.path.exists(result.system_path)

    def test_stop_returns_dual_track_result(self, tmp_path):
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        rec.feed_mic(_gen_pcm_sine(duration_s=0.5))
        rec.feed_system(_gen_pcm_sine(freq=880, duration_s=0.5))
        result = rec.stop()
        assert isinstance(result, DualTrackResult)
        assert result.mic_samples > 0
        assert result.system_samples > 0
        assert result.duration_s > 0
        assert result.sample_rate == 16000
        assert result.channels == 1

    def test_stop_returns_within_timeout(self, tmp_path):
        """T3.3: stop() deve retornar em menos de 2s."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        t0 = time.monotonic()
        rec.stop(timeout_s=2.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0, f"stop() demorou {elapsed:.2f}s"

    def test_start_idempotent(self, tmp_path):
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        mic_path_first = rec.mic_path
        rec.start()  # não deve recriar arquivos
        assert rec.mic_path == mic_path_first
        rec.stop()

    def test_stop_without_start_returns_empty_result(self, tmp_path):
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        result = rec.stop()
        assert isinstance(result, DualTrackResult)
        assert result.mic_samples == 0
        assert result.system_samples == 0

    def test_feed_before_start_is_ignored(self, tmp_path):
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        # Não deve lançar exceção
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        rec.feed_system(_gen_pcm_sine(duration_s=0.1))
        rec.start()
        result = rec.stop()
        assert result.mic_samples == 0


class TestDualTrackRecorderContent:
    """Testes do conteúdo gravado nos arquivos WAV."""

    def test_mic_and_system_independent(self, tmp_path):
        """T3.1 (unitário): trilhos não se cruzam — cada um tem só o seu conteúdo."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        # Mic: 440 Hz; Sistema: 880 Hz
        mic_chunk = _gen_pcm_sine(freq=440, duration_s=0.5)
        sys_chunk = _gen_pcm_sine(freq=880, duration_s=0.5)
        rec.feed_mic(mic_chunk)
        rec.feed_system(sys_chunk)
        result = rec.stop()

        with wave.open(result.mic_path, "rb") as wf_mic, \
             wave.open(result.system_path, "rb") as wf_sys:
            mic_data = np.frombuffer(wf_mic.readframes(wf_mic.getnframes()),
                                     dtype=np.int16).astype(np.float32)
            sys_data = np.frombuffer(wf_sys.readframes(wf_sys.getnframes()),
                                     dtype=np.int16).astype(np.float32)

        # FFT para identificar a frequência dominante
        mic_fft = np.abs(np.fft.rfft(mic_data))
        sys_fft = np.abs(np.fft.rfft(sys_data))
        mic_peak_freq = np.argmax(mic_fft) * (16000 / len(mic_data))
        sys_peak_freq = np.argmax(sys_fft) * (16000 / len(sys_data))

        # Mic deve ter pico próximo a 440 Hz, sistema a 880 Hz
        assert abs(mic_peak_freq - 440) < 30, (
            f"Mic esperado ~440Hz, obtido {mic_peak_freq:.1f}Hz"
        )
        assert abs(sys_peak_freq - 880) < 30, (
            f"Sistema esperado ~880Hz, obtido {sys_peak_freq:.1f}Hz"
        )

    def test_wav_format_is_pcm16_mono_16k(self, tmp_path):
        """Valida formato do WAV gerado."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t", sample_rate=16000)
        rec.start()
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        result = rec.stop()
        with wave.open(result.mic_path, "rb") as wf:
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000

    def test_durations_within_tolerance(self, tmp_path):
        """T3.1 (unitário): durações dos dois trilhos próximas."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t", sample_rate=16000)
        rec.start()
        # Mesma duração em ambos
        for _ in range(5):
            rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
            rec.feed_system(_gen_pcm_sine(freq=880, duration_s=0.1))
        result = rec.stop()

        mic_dur = result.mic_samples / 16000
        sys_dur = result.system_samples / 16000
        diff_ms = abs(mic_dur - sys_dur) * 1000
        # T3.1 exige diff <= 100ms em integração; aqui no unitário
        # esperamos ~0ms porque alimentamos a mesma quantidade.
        assert diff_ms < 50, (
            f"Diff de duração muito alta: {diff_ms:.1f}ms"
        )

    def test_start_monotonic_recorded_on_first_frame(self, tmp_path):
        """T3.2 (unitário): timestamp de início é registrado no primeiro frame."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        # Antes de alimentar, first_frame_monotonic é None
        assert rec._mic_writer.first_frame_monotonic is None
        time.sleep(0.05)
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        # Após alimentar, foi registrado
        assert rec._mic_writer.first_frame_monotonic is not None
        rec.stop()

    def test_5_cycles_start_stop(self, tmp_path):
        """T3.4 (unitário): 5 ciclos start/stop sem corrupção."""
        for i in range(5):
            rec = DualTrackRecorder(str(tmp_path), prefix=f"cycle{i}")
            rec.start()
            rec.feed_mic(_gen_pcm_sine(duration_s=0.05))
            rec.feed_system(_gen_pcm_sine(freq=880, duration_s=0.05))
            result = rec.stop()
            assert result.mic_samples > 0
            assert result.system_samples > 0
            # Arquivo deve ser WAV válido
            with wave.open(result.mic_path, "rb") as wf:
                assert wf.getnframes() > 0


class TestDualTrackRecorderConcurrency:
    """Testes de thread-safety do recorder."""

    def test_concurrent_feed_from_two_threads(self, tmp_path):
        """Feed mic e system a partir de threads distintas não corrompe."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()

        def feed_mic():
            for _ in range(20):
                rec.feed_mic(_gen_pcm_sine(duration_s=0.01))
                time.sleep(0.001)

        def feed_system():
            for _ in range(20):
                rec.feed_system(_gen_pcm_sine(freq=880, duration_s=0.01))
                time.sleep(0.001)

        t1 = threading.Thread(target=feed_mic)
        t2 = threading.Thread(target=feed_system)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        result = rec.stop()
        # Cada thread alimentou 20 * 160 amostras = 3200 amostras
        assert result.mic_samples == 3200
        assert result.system_samples == 3200

    def test_partial_frame_at_stop_is_flushed(self, tmp_path):
        """T3.3 (unitário): último frame antes do stop é preservado."""
        rec = DualTrackRecorder(str(tmp_path), prefix="t")
        rec.start()
        # Alimenta um frame "completo"
        rec.feed_mic(_gen_pcm_sine(duration_s=0.1))
        # E imediatamente outro pequeno antes do stop
        rec.feed_mic(_gen_pcm_sine(duration_s=0.02))
        result = rec.stop()
        # Deve ter gravado tudo (0.1 + 0.02 = 0.12s = 1920 amostras)
        assert result.mic_samples == 1920
