"""MET-01..MET-05 — Testes metamórficos da captura e mixagem.

Metamorfismo: alteração controlada da entrada deve produzir alteração
**previsível** na saída. Violação da relação prevista = regressão de
qualidade — mesmo sem valor absoluto de referência.

Classificação honesta:
- MET-01/02/03/04: integração com código real (offline, device sintético
  + geradores determinísticos);
- MET-05: integração real com o ``AudioMixer`` do produto (AGC real).
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.fidelity import dsp_utils as dsp
from tests.fidelity.fake_device import run_pipewire_capture
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
CHUNK = 480


def _collect_signal(sig: np.ndarray, chunk_frames: int = CHUNK) -> np.ndarray:
    """Roda o sinal pelo caminho REAL de captura e devolve o sinal publicado."""
    n = (len(sig) // chunk_frames) * chunk_frames
    _, chunks, _ = run_pipewire_capture(sig[:n], sample_rate=SR,
                                        chunk_frames=chunk_frames)
    return sg.pcm_s16le_to_float(b"".join(chunks), channels=1)


# ---------------------------------------------------------------------------
# MET-01 — Ganho de entrada escala RMS de modo previsível
# ---------------------------------------------------------------------------

class TestMet01GainScalesRms:
    @pytest.mark.parametrize("gain", [0.25, 0.5, 2.0, 4.0])
    def test_gain_scales_rms_exactly(self, gain):
        """Escalar a entrada por ``gain`` deve escalar o RMS pelo mesmo
        fator linear (±0.5 dB ≈ ±6%) no caminho real de captura —
        relação linear amplitude→amplitude (comparação linear, sem
        ambiguidade 10×/20× logarítmica)."""
        import math

        base = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=21,
                              amplitude=0.2)
        scaled = np.clip(base * gain, -1.0, 1.0)
        out_base = _collect_signal(base)
        out_scaled = _collect_signal(scaled)
        ratio = dsp.rms(out_scaled) / dsp.rms(out_base)
        assert math.isclose(ratio, gain, rel_tol=0.06), (
            f"ganho {gain}x: RMS mudou por fator {ratio:.4f} "
            f"(esperado {gain}, ±6% ≈ ±0.5 dB)"
        )

    def test_gain_relation_breaks_when_clipping(self):
        """A relação prevista VIOLA quando o ganho satura o sinal —
        garante que o teste detecta clipping real (não tautológico)."""
        base = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                       amplitude=0.9)
        saturated = np.clip(base * 4.0, -1.0, 1.0)  # ganho 4x com clipping
        out_base = _collect_signal(base)
        out_sat = _collect_signal(saturated)
        ratio = dsp.rms(out_sat) / dsp.rms(out_base)
        # Sem clipping seria 4.0; saturação segura o crescimento abaixo
        # de 4 * 10^(-1/20) ≈ 3.56 (margem de 1 dB abaixo do linear)
        assert ratio < 3.56, (
            f"RMS cresceu quase linearmente ({ratio:.3f}x) mesmo com "
            "saturação — detector metamórfico de clipping falhou"
        )


# ---------------------------------------------------------------------------
# MET-02 — chunk_frames não altera materialmente energia/duração
# ---------------------------------------------------------------------------

class TestMet02ChunkSizeInvariance:
    def test_energy_and_duration_invariant_to_chunk_size(self):
        """Mesma entrada, chunk_frames distintos ⇒ energia/duração iguais.

        Duração 1.2 s = 19200 samples é múltiplo de 160, 480 e 960 —
        sem descarte de cauda, permitindo comparação exata.
        """
        sig = sg.speech_like(duration_s=1.2, sample_rate=SR, seed=22,
                             amplitude=0.4)
        assert len(sig) == 19200
        results = {}
        for cf in (160, 480, 960):
            out = _collect_signal(sig, chunk_frames=cf)
            results[cf] = out
            assert len(out) == len(sig), (
                f"duração mudou com chunk_frames={cf}"
            )
        energies = [dsp.total_energy(results[cf]) for cf in (160, 480, 960)]
        assert max(energies) - min(energies) < 1e-6, (
            f"energia variou entre chunk sizes: {energies}"
        )

    def test_content_identical_across_chunk_sizes(self):
        """Conteúdo publicado bit a bit idêntico entre tamanhos de chunk."""
        sig = sg.sine(freq_hz=440.0, duration_s=1.2, sample_rate=SR,
                      amplitude=0.5)
        sig = sig[: (len(sig) // 960) * 960]
        outs = [_collect_signal(sig, chunk_frames=cf) for cf in (160, 480, 960)]
        np.testing.assert_array_equal(outs[0], outs[1])
        np.testing.assert_array_equal(outs[1], outs[2])


# ---------------------------------------------------------------------------
# MET-03 — Resampling preserva duração temporal
# ---------------------------------------------------------------------------

class TestMet03ResampleDuration:
    def test_resample_preserves_duration(self):
        """44100 → 16000: duração preservada (±1 sample de arredondamento)."""
        sig44 = sg.sine(freq_hz=1000.0, duration_s=2.0, sample_rate=44100,
                        amplitude=0.5)
        out16 = sg.resample(sig44, 44100, 16000)
        expected_n = len(sig44) * 16000 / 44100
        assert abs(len(out16) - expected_n) <= 1.0, (
            f"duração após resample: {len(out16)} samples vs esperado "
            f"{expected_n:.1f}"
        )

    def test_resample_roundtrip_preserves_duration(self):
        """16k → 8k → 16k: duração preservada (±1 sample)."""
        sig = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=23,
                             amplitude=0.3)
        mid = sg.resample(sig, SR, 8000)
        back = sg.resample(mid, 8000, SR)
        assert abs(len(back) - len(sig)) <= 1

    def test_resample_preserves_spectral_peak(self):
        """Pico espectral sobrevive ao resample 16k→8k (sem aliasing do
        componente principal: 1 kHz bem abaixo de Nyquist/2)."""
        sig = sg.sine(freq_hz=1000.0, duration_s=2.0, sample_rate=SR,
                      amplitude=0.5)
        out = sg.resample(sig, SR, 8000)
        peak = dsp.spectral_peak_hz(out, 8000)
        assert abs(peak - 1000.0) < 5.0


# ---------------------------------------------------------------------------
# MET-04 — Permutação de canais estéreo não quebra contratos
# ---------------------------------------------------------------------------

class TestMet04StereoPermutation:
    def test_channel_permutation_downmix_invariant(self):
        """Trocar L↔R não altera o downmix mono (média é comutativa) —
        invariância da qual o pipeline mono depende."""
        x = sg.speech_like(duration_s=1.5, sample_rate=SR, seed=24,
                           amplitude=0.3)
        st = sg.to_stereo(x, mode="half")
        permuted = st[:, ::-1].copy()  # troca L/R
        np.testing.assert_allclose(
            sg.downmix_mono(st), sg.downmix_mono(permuted), atol=1e-15
        )

    def test_permuted_channels_still_satisfy_mono_contract(self):
        """Canais permutados continuam decodificáveis no formato canônico:
        cada canal, capturado como mono, produz PCM s16le válido com RMS
        equivalente (energia por canal preservada pela permutação)."""
        x = sg.speech_like(duration_s=1.5, sample_rate=SR, seed=25,
                           amplitude=0.3)
        st = sg.to_stereo(x, mode="half")
        permuted = st[:, ::-1].copy()
        for name, ch in (("L", st[:, 0]), ("R", st[:, 1]),
                         ("L'", permuted[:, 0]), ("R'", permuted[:, 1])):
            pcm = sg.float_to_pcm_s16le(ch)
            assert len(pcm) % 2 == 0
            arr = np.frombuffer(pcm, dtype=np.int16)
            assert arr.size == len(ch)
        assert dsp.rms(permuted[:, 0]) == pytest.approx(dsp.rms(st[:, 1]))
        assert dsp.rms(permuted[:, 1]) == pytest.approx(dsp.rms(st[:, 0]))

    def test_permutation_detectable_in_antiphase_case(self):
        """Caso adversário: antifase + permutação continua anulando o
        downmix — o detector de energia revela o problema de canais."""
        x = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                    amplitude=0.3)
        st = sg.to_stereo(x, mode="antiphase")
        permuted = st[:, ::-1].copy()
        assert dsp.rms(sg.downmix_mono(st)) < 1e-9
        assert dsp.rms(sg.downmix_mono(permuted)) < 1e-9


# ---------------------------------------------------------------------------
# MET-05 — AGC do mixer: relações de ganho previsíveis (produto real)
# ---------------------------------------------------------------------------

class TestMet05MixerAgc:
    def _mix(self, frame: bytes) -> bytes:
        from src.audio.mixer import AudioMixer

        mixer = AudioMixer(sample_rate=SR, channels=1)
        return mixer.mix_frame(frame, frame)

    def test_agc_attenuates_loud_to_target(self):
        """Sinal alto (acima do target): AGC atenua para ~target_rms.

        Dois trilhos idênticos e altos: cada um normalizado para 0.05,
        média (a+b)/2 mantém ~0.05 → relação previsível e estável.
        """
        from src.audio.mixer import AudioMixer

        target = 0.05
        loud = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                       amplitude=0.8)
        frame = sg.float_to_pcm_s16le(loud)
        mixer = AudioMixer(sample_rate=SR, channels=1)
        out = mixer.mix_frame(frame, frame)
        out_sig = sg.pcm_s16le_to_float(out)
        assert dsp.rms(out_sig) == pytest.approx(target, rel=0.35), (
            f"AGC deveria aproximar RMS de {target}, obtido "
            f"{dsp.rms(out_sig):.4f}"
        )

    def test_agc_metamorphic_louder_input_same_output(self):
        """Relação metamórfica REAL do AGC: aumentar a amplitude de um
        sinal já alto NÃO aumenta a saída (limitador de normalização)."""
        loud1 = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                        amplitude=0.6)
        loud2 = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                        amplitude=0.9)
        out1 = sg.pcm_s16le_to_float(self._mix(sg.float_to_pcm_s16le(loud1)))
        out2 = sg.pcm_s16le_to_float(self._mix(sg.float_to_pcm_s16le(loud2)))
        assert dsp.rms(out2) == pytest.approx(dsp.rms(out1), rel=0.25), (
            "AGC deveria ser invariante à amplitude de entradas altas — "
            "relação metamórfica violada"
        )

    def test_no_agc_linear_metamorphic(self):
        """Sem AGC (target_rms=None): dobrar a entrada dobra a saída
        (relação linear exata do caminho (a+b)/2 com clamp)."""
        from src.audio.mixer import AudioMixer

        base = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                       amplitude=0.2)
        doubled = base * 2.0
        mixer = AudioMixer(sample_rate=SR, channels=1, target_rms=None)
        out_base = sg.pcm_s16le_to_float(
            mixer.mix_frame(sg.float_to_pcm_s16le(base),
                            sg.float_to_pcm_s16le(base)))
        out_double = sg.pcm_s16le_to_float(
            mixer.mix_frame(sg.float_to_pcm_s16le(doubled),
                            sg.float_to_pcm_s16le(doubled)))
        assert dsp.rms(out_double) == pytest.approx(2.0 * dsp.rms(out_base),
                                                    rel=0.02)

    def test_single_source_passthrough_metamorphic(self):
        """Fonte única passa intocada (T4.3 do produto): ganho 1.0 exato."""
        from src.audio.mixer import AudioMixer

        x = sg.speech_like(duration_s=1.0, sample_rate=SR, seed=26,
                           amplitude=0.3)
        mixer = AudioMixer(sample_rate=SR, channels=1)
        frame = sg.float_to_pcm_s16le(x)
        out = mixer.mix_frame(frame, None)
        assert out == bytes(frame), "fonte única deveria passar bit a bit"
        out2 = mixer.mix_frame(None, frame)
        assert out2 == bytes(frame)
