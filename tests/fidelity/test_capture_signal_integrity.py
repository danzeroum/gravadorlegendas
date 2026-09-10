"""FID-01..FID-06 — Integridade de sinal no caminho digital de captura.

Classificação honesta dos testes deste arquivo (ver README de
docs/qualidade-audio/):

- **integração com código real (offline)**: sinais sintéticos f32 são
  bombeados pelo loop de conversão REAL do ``PipewireCapture``
  (``_capture_loop``/``_pump_stdout`` — thread, sanitização NaN/Inf,
  conversão f32→s16le, publicação em fila) via subprocesso fake. Sem
  hardware PipeWire: apenas o *device* é sintético.
- **sintético puro**: propriedades DSP avaliadas diretamente nos
  geradores/corpus (downmix, energia, DC), rotuladas no próprio teste.

Testes com hardware/loopback real estão em tests/integration/ com marker
``requires_pipewire`` (inalterados nesta suíte).
"""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from tests.fidelity import dsp_utils as dsp
from tests.fidelity.fake_device import run_pipewire_capture
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
CHUNK = 480


def _chunks_to_signal(chunks: list[bytes]) -> np.ndarray:
    """Concatena chunks PCM s16le publicados pelo backend em sinal float."""
    raw = b"".join(chunks)
    return sg.pcm_s16le_to_float(raw, channels=1)


# ---------------------------------------------------------------------------
# FID-01 — Pico espectral da senoide de 1 kHz (±5 Hz, sem resampling)
# ---------------------------------------------------------------------------

class TestFid01SpectralPeak:
    def test_peak_1khz_through_real_capture_path(self, corpus_scenario):
        """Senoide 1 kHz atravessa o caminho REAL de conversão do backend.

        O pipeline sob teste não introduz resampling intencional (pw-record
        é chamado com --rate 16000 e o pump faz conversão de formato apenas),
        então o pico espectral deve permanecer em 1 kHz ± tolerância do
        manifesto (5 Hz).
        """
        scen = corpus_scenario["sine_1k"]
        tol = scen["thresholds"]["spectral_peak_hz_tol"]
        sig = sg.sine(freq_hz=1000.0, duration_s=3.0, sample_rate=SR,
                      amplitude=0.5)
        _, chunks, holder = run_pipewire_capture(sig, sample_rate=SR,
                                                 chunk_frames=CHUNK)
        # O comando real deve pedir a taxa alvo sem reamostragem implícita
        cmd = holder["cmd"]
        assert "--rate" in cmd and str(SR) in cmd
        out = _chunks_to_signal(chunks)
        peak = dsp.spectral_peak_hz(out, SR)
        assert abs(peak - 1000.0) <= tol, (
            f"Pico espectral {peak:.2f} Hz fora de ±{tol} Hz de 1000 Hz"
        )

    def test_peak_1khz_corpus_fixture(self, corpus_scenario, corpus_audio_dir):
        """Fixture versionada do corpus mantém o pico em 1 kHz."""
        scen = corpus_scenario["sine_1k"]
        tol = scen["thresholds"]["spectral_peak_hz_tol"]
        x, sr = sf.read(str(corpus_audio_dir / "sine_1k.wav"), dtype="float64")
        assert sr == SR
        peak = dsp.spectral_peak_hz(x, sr)
        assert abs(peak - 1000.0) <= tol

    def test_peak_detects_wrong_frequency(self):
        """A métrica FALHA quando a propriedade é violada de fato.

        Senoide deslocada (1030 Hz) deve ser detectada fora da tolerância
        de ±5 Hz — garante que o teste não é tautológico.
        """
        sig = sg.sine(freq_hz=1030.0, duration_s=2.0, sample_rate=SR,
                      amplitude=0.5)
        peak = dsp.spectral_peak_hz(sig, SR)
        assert abs(peak - 1000.0) > 5.0


# ---------------------------------------------------------------------------
# FID-02 — RMS em ±1 dB contra referência (caminho digital controlado)
# ---------------------------------------------------------------------------

class TestFid02Rms:
    @pytest.mark.parametrize("amplitude", [0.5, 0.25, 0.05])
    def test_rms_within_1db_through_real_capture_path(
        self, corpus_scenario, amplitude
    ):
        """RMS do sinal convertido fica a ±1 dB do RMS analítico.

        RMS teórico da senoide = amplitude/√2. A quantização s16 e a
        conversão f32→int16 do backend são praticamente lossless nesse
        nível, então a tolerância de ±1 dB (manifesto) é folgada e estável.
        """
        scen = corpus_scenario["sine_1k"]
        tol_db = scen["thresholds"]["rms_db_tol"]
        sig = sg.sine(freq_hz=1000.0, duration_s=2.0, sample_rate=SR,
                      amplitude=amplitude)
        expected_rms = amplitude / np.sqrt(2.0)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        out = _chunks_to_signal(chunks)
        measured_rms = dsp.rms(out)
        ratio_db = dsp.db(measured_rms, expected_rms)
        assert abs(ratio_db) <= tol_db, (
            f"RMS medido {measured_rms:.5f} vs esperado {expected_rms:.5f} "
            f"({ratio_db:+.2f} dB, tolerância ±{tol_db} dB)"
        )

    def test_rms_detects_level_regression(self):
        """A métrica detecta queda de nível de 3 dB (violação real)."""
        a = sg.sine(freq_hz=1000.0, duration_s=2.0, sample_rate=SR,
                    amplitude=0.5)
        b = sg.sine(freq_hz=1000.0, duration_s=2.0, sample_rate=SR,
                    amplitude=0.5 * 10 ** (-3.0 / 20.0))  # -3 dB
        ratio_db = dsp.db(dsp.rms(b), dsp.rms(a))
        assert ratio_db < -1.0, "queda de 3 dB deveria violar a tolerância ±1 dB"


# ---------------------------------------------------------------------------
# FID-03 — Amostras no intervalo normalizado, sem clipping introduzido
# ---------------------------------------------------------------------------

class TestFid03RangeNoClipping:
    def test_no_clipping_introduced_by_capture_path(self):
        """Pseudo-fala de pico 0.4 atravessa o caminho real sem saturar.

        A fração de amostras nos trilhos após a conversão deve permanecer
        desprezível (o sinal limpo tem ~1e-5).
        """
        sig = sg.speech_like(duration_s=4.0, sample_rate=SR, seed=7,
                             amplitude=0.4)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        out = _chunks_to_signal(chunks)
        assert dsp.sample_range(out)[0] >= -1.0
        assert dsp.sample_range(out)[1] <= 1.0
        rail = dsp.clipped_fraction(out)
        assert rail < 0.001, (
            f"caminho de captura introduziu clipping (rail={rail:.5f})"
        )

    def test_int16_range_respected(self):
        """Valores int16 publicados ficam em [-32768, 32767]."""
        sig = sg.sine(freq_hz=440.0, duration_s=1.5, sample_rate=SR,
                      amplitude=0.99)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        raw = b"".join(chunks)
        arr = np.frombuffer(raw, dtype=np.int16)
        assert int(arr.min()) >= -32768
        assert int(arr.max()) <= 32767
        # Amplitude 0.99 deve mapear para perto do full-scale sem passar
        assert int(arr.max()) <= int(np.rint(0.99 * 32767)) + 1

    def test_clipping_fixture_is_detectable(self, corpus_audio_dir):
        """A métrica de rail-hit detecta clipping real (não tautológica).

        Fixture deliberadamente clipada (±0.25) tem fração de trilho
        muito acima do limiar do manifesto.
        """
        cl, _ = sf.read(str(corpus_audio_dir / "clipped.wav"), dtype="float64")
        rail = dsp.clipped_fraction(cl)
        assert rail >= 0.02, f"clipping deveria ser detectado, rail={rail:.4f}"


# ---------------------------------------------------------------------------
# FID-05 — Downmix mono/estéreo preservando energia
# ---------------------------------------------------------------------------

class TestFid05DownmixEnergy:
    """Classificação: sintético puro (propriedade DSP) + contrato de
    formato do backend (o produto captura mono; pw-record faz o downmix
    no servidor — aqui validamos a propriedade que o downmix deve ter).
    """

    def test_duplicated_stereo_downmix_preserves_signal(self):
        x = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=11,
                           amplitude=0.3)
        mono = sg.downmix_mono(sg.to_stereo(x, mode="duplicated"))
        np.testing.assert_allclose(mono, x, atol=1e-12)

    def test_half_stereo_downmix_preserves_energy(self):
        """Downmix por média de canais x/√2: energia mono = metade da
        estéreo (dentro de ±0.1 dB) — padrão de preservação de energia."""
        x = sg.speech_like(duration_s=2.0, sample_rate=SR, seed=12,
                           amplitude=0.3)
        st = sg.to_stereo(x, mode="half")
        mono = sg.downmix_mono(st)
        e_mono = dsp.total_energy(mono)
        e_st = dsp.total_energy(st)
        ratio_db = dsp.db(e_mono, e_st)
        assert abs(ratio_db - (-3.01)) < 0.1, (
            f"energia do downmix {ratio_db:.2f} dB (esperado -3.01 dB)"
        )

    def test_antiphase_downmix_to_zero_is_detectable(self):
        """Caso adversário: canais em antifase se anulam no downmix.

        O detector de energia deve registrar perda total — se o pipeline
        estivesse com canais invertidos, esta métrica revelaria.
        """
        x = sg.speech_like(duration_s=1.0, sample_rate=SR, seed=13,
                           amplitude=0.3)
        mono = sg.downmix_mono(sg.to_stereo(x, mode="antiphase"))
        assert dsp.rms(mono) < 1e-9

    def test_backend_requests_mono_channel(self):
        """Contrato: o comando real do pw-record pede --channels 1."""
        from src.audio.backends.pipewire.capture import PipewireCapture

        cap = PipewireCapture(device_id="42", sample_rate=SR, chunk_size=CHUNK)
        cmd = cap._build_cmd()
        assert "--channels" in cmd
        assert cmd[cmd.index("--channels") + 1] == "1"


# ---------------------------------------------------------------------------
# FID-06 — DC offset baixo
# ---------------------------------------------------------------------------

class TestFid06DcOffset:
    def test_dc_offset_negligible_through_capture_path(self):
        """Sinal de média zero atravessa o caminho real com DC ~0.

        Tolerância 1e-3: muito acima do ruído de quantização s16 (~1e-4
        para sinais de 0.4 de amplitude) e muito abaixo de qualquer DC
        patológico que indicaria bug de conversão.
        """
        sig = sg.speech_like(duration_s=3.0, sample_rate=SR, seed=7,
                             amplitude=0.4)
        _, chunks, _ = run_pipewire_capture(sig, sample_rate=SR,
                                            chunk_frames=CHUNK)
        out = _chunks_to_signal(chunks)
        dc = dsp.dc_offset(out)
        assert abs(dc) < 1e-3, f"DC offset {dc:.6f} acima do limiar 1e-3"

    def test_dc_offset_silence_fixture_is_exact_zero(self, corpus_audio_dir):
        x, _ = sf.read(str(corpus_audio_dir / "silence.wav"), dtype="float64")
        assert dsp.dc_offset(x) == 0.0
        assert dsp.rms(x) == 0.0

    def test_dc_offset_detector_catches_adversarial_case(self):
        """A métrica detecta DC offset patológico (violação real)."""
        x = sg.speech_like(duration_s=1.0, sample_rate=SR, seed=14,
                           amplitude=0.3)
        biased = sg.add_dc_offset(x, 0.05)
        assert abs(dsp.dc_offset(biased)) > 1e-3
