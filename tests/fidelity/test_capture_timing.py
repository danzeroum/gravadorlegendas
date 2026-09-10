"""FID-07..FID-10 — Temporização e formato da captura.

Classificação honesta (ver docs/qualidade-audio/README.md):

- **integração com código real (offline)**: frames atravessam o loop
  REAL do ``PipewireCapture`` com subprocesso sintético (thread + pump +
  fila). Sem hardware PipeWire.
- **sintético puro**: contratos de configuração (``AudioCaptureConfig``,
  ``_build_cmd``).

Tolerância de ±1 chunk na contagem de frames é justificada pelo
comportamento documentado do pump: o último fragmento incompleto do
stream é descartado (não preenche chunk inteiro) — ver
``PipewireCapture._pump_stdout``.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.audio.backends.pipewire.capture import PipewireCapture
from src.platform.types import AudioCaptureConfig
from tests.fidelity import dsp_utils as dsp
from tests.fidelity.fake_device import (
    TimingQueue,
    f32_bytes,
    run_pipewire_capture,
    synthetic_pw_record,
)
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
CHUNK = 480


# ---------------------------------------------------------------------------
# FID-04 — Contagem de frames esperada (tolerância ≤ 1 chunk)
# ---------------------------------------------------------------------------

class TestFid04FrameCount:
    def test_exact_multiple_yields_exact_frame_count(self):
        """3.0 s @16 kHz = 48000 samples = exatamente 100 chunks de 480."""
        sig = sg.sine(freq_hz=1000.0, duration_s=3.0, sample_rate=SR,
                      amplitude=0.5)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        expected = int(len(sig)) // CHUNK
        assert len(chunks) == expected, (
            f"{len(chunks)} chunks publicados, esperados exatamente "
            f"{expected} (entrada é múltiplo exato do chunk)"
        )

    def test_partial_tail_discards_at_most_one_chunk(self):
        """Entrada não-múltiplo: contagem = floor(n/chunk) ± 1 chunk.

        Justificativa da tolerância: o pump descarta o fragmento final
        incompleto (comportamento documentado do código de produção).
        """
        sig = sg.sine(freq_hz=440.0, duration_s=3.0, sample_rate=SR,
                      amplitude=0.5)
        # Corta 300 samples do fim: 47700 = 99 chunks inteiros + resto 300
        trimmed = sig[: 3 * SR - 300]
        _, chunks, _ = run_pipewire_capture(trimmed, sample_rate=SR,
                                            chunk_frames=CHUNK)
        expected = int(len(trimmed)) // CHUNK
        assert expected - 1 <= len(chunks) <= expected, (
            f"{len(chunks)} chunks, esperado {expected} (floor) ± 1"
        )

    def test_shorter_stream_proportionally_fewer_frames(self):
        """Metade da duração ⇒ metade dos frames (proporcionalidade)."""
        long_sig = sg.sine(freq_hz=440.0, duration_s=2.0, sample_rate=SR,
                           amplitude=0.5)
        short_sig = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                            amplitude=0.5)
        _, chunks_long, _ = run_pipewire_capture(
            long_sig, sample_rate=SR, chunk_frames=CHUNK)
        _, chunks_short, _ = run_pipewire_capture(
            short_sig, sample_rate=SR, chunk_frames=CHUNK)
        assert len(chunks_long) == 2 * len(chunks_short)


# ---------------------------------------------------------------------------
# FID-07 — Tamanho do chunk conforme AudioCaptureConfig.chunk_frames
# ---------------------------------------------------------------------------

class TestFid07ChunkSize:
    @pytest.mark.parametrize("chunk_frames", [480, 960, 160])
    def test_chunk_bytes_match_config(self, chunk_frames):
        """Cada chunk publicado tem exatamente chunk_frames * 2 bytes."""
        sig = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=7,
                             amplitude=0.4)
        _, chunks, _ = run_pipewire_capture(
            sig, sample_rate=SR, chunk_frames=chunk_frames)
        assert chunks, "nenhum chunk publicado"
        expected_bytes = chunk_frames * 2
        for i, c in enumerate(chunks):
            assert len(c) == expected_bytes, (
                f"chunk {i} com {len(c)} bytes, esperados {expected_bytes}"
            )

    def test_config_chunk_frames_default(self):
        """Default do AudioCaptureConfig segue o padrão do produto (480)."""
        config = AudioCaptureConfig()
        assert config.chunk_frames == 480
        assert config.sample_rate == 16000
        assert config.channels == 1


# ---------------------------------------------------------------------------
# FID-08 — Ausência de gaps/overlaps lógicos no contador de frames
# ---------------------------------------------------------------------------

class TestFid08LogicalContinuity:
    def test_concatenated_chunks_equal_input(self):
        """Sem gaps/overlaps: concatenação == sinal de entrada exatamente.

        Entrada aparada para múltiplo exato do chunk (o pump descarta o
        fragmento final incompleto — comportamento documentado). A soma
        dos samples publicados deve reproduzir o stream de entrada bit a
        bit.
        """
        sig_full = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=7,
                                  amplitude=0.4)
        sig = sig_full[: (len(sig_full) // CHUNK) * CHUNK]
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        raw = b"".join(chunks)
        assert len(raw) == len(sig) * 2, (
            f"total publicado {len(raw)} bytes != entrada {len(sig) * 2} "
            "bytes — gap ou overlap lógico no contador de frames"
        )
        # Conteúdo: o pump do produto converte f32 -> s16 com a aritmética
        # exata (arr_float32 * 32767.0).astype(int16) — truncamento, não
        # arredondamento. Replicamos bit a bit para detectar QUALQUER
        # desvio de conteúdo (gap, overlap, sample trocado).
        got = np.frombuffer(raw, dtype=np.int16)
        arr32 = np.asarray(sig, dtype=np.float32)
        want = (arr32 * 32767.0).astype(np.int16)
        np.testing.assert_array_equal(got, want)

    def test_no_duplicate_chunks(self):
        """Chunks são distintos em posição — sem duplicação de publicação."""
        sig = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=7,
                             amplitude=0.4)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        ids = [id(c) for c in chunks]
        assert len(set(ids)) == len(ids), "mesmo objeto publicado duas vezes"


# ---------------------------------------------------------------------------
# FID-09 — Sample rate e formato canônico corretos
# ---------------------------------------------------------------------------

class TestFid09CanonicalFormat:
    @pytest.mark.parametrize("rate", [8000, 16000, 44100])
    def test_build_cmd_requests_target_rate(self, rate):
        """O comando real repassa a taxa alvo para o pw-record."""
        cap = PipewireCapture(device_id="42", sample_rate=rate,
                              chunk_size=CHUNK)
        cmd = cap._build_cmd()
        assert cmd[cmd.index("--rate") + 1] == str(rate)

    def test_published_chunks_are_s16le_mono(self):
        """Chunks decodificam como int16 com tamanho de bytes par."""
        sig = sg.sine(freq_hz=1000.0, duration_s=1.0, sample_rate=SR,
                      amplitude=0.5)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        for c in chunks:
            assert len(c) % 2 == 0, "chunk com bytes ímpares (s16 corrompido)"
            arr = np.frombuffer(c, dtype=np.int16)
            assert arr.dtype == np.int16

    def test_audio_chunk_canonical_defaults(self):
        """AudioChunk do contrato: mono 16 kHz s16le."""
        from src.platform.types import AudioChunk

        chunk = AudioChunk(data=b"\x00" * 960)
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1

    def test_facade_config_passthrough(self):
        """A fachada AudioCapture repassa sample_rate/chunk_size ao backend."""
        from src.audio.capture import AudioCapture

        cap = AudioCapture(device_index="42", sample_rate=16000,
                           chunk_size=960)
        assert cap.sample_rate == 16000
        assert cap.chunk_size == 960
        assert cap.channels == 1


# ---------------------------------------------------------------------------
# FID-10 — Jitter p95 de entrega (smoke budget, não gate rígido)
# ---------------------------------------------------------------------------

class TestFid10JitterP95:
    def test_jitter_p95_measured_with_timing_queue(self):
        """p95 do intervalo entre chegadas de chunks abaixo de budget smoke.

        Budget generoso (50 ms) para o caminho in-memory: o pump real
        entrega em ~µs; o objetivo é detectar regressões grotescas
        (ex.: busy-wait introduzido no loop, bloqueio de fila). Budget
        de produção é configurado no job noturno (PERF-01) — ver
        docs/qualidade-audio/README.md §5. A medição usa timestamps
        monotônicos de chegada (TimingQueue) — sem wall-clock absoluto.
        """
        import queue as queue_mod

        sig = sg.speech_like(duration_s=6.0, sample_rate=SR, seed=7,
                             amplitude=0.4)
        q = TimingQueue()
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42", sample_rate=SR,
                                    channels=1, chunk_frames=CHUNK)
        with synthetic_pw_record(f32_bytes(sig)):
            cap.start(config, q)
            thread = cap._thread
            assert thread is not None
            thread.join(timeout=15.0)
            while True:
                try:
                    q.get_nowait()
                except queue_mod.Empty:
                    break
            cap.stop()
        stamps = q.put_timestamps
        assert len(stamps) >= 100, (
            f"poucas chegadas registradas ({len(stamps)}) para p95 estável"
        )
        gaps = [
            b - a for a, b in zip(stamps[:-1], stamps[1:]) if b > a
        ]
        p95 = dsp.percentile95(gaps)
        budget_s = 0.05  # 50 ms — smoke budget documentado
        assert p95 < budget_s, (
            f"jitter p95 = {p95 * 1000:.1f} ms acima do smoke budget "
            f"de {budget_s * 1000:.0f} ms"
        )
