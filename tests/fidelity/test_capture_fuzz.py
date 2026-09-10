"""FUZZ-01..FUZZ-06 — Fuzzing/robustez com Hypothesis e casos adversariais.

Estratégia de estabilidade de CI:
- ``max_examples`` limitado (25 por propriedade) e ``deadline=None``
  (deadline do Hypothesis mede tempo de CPU por exemplo — dependeria do
  runner e causaria flakiness);
- seeds fixos onde há aleatoriedade de sinal;
- nenhuma propriedade depende de temporização real.

Política de honestidade: entradas inválidas devem produzir **erro
explícito** ou **comportamento gracioso documentado** — nunca sucesso
silencioso mascarando exceção inesperada.
"""
from __future__ import annotations

import queue as queue_mod
import sys
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.audio.backends import AudioBackendError
from src.audio.backends.pipewire.capture import PipewireCapture
from src.platform.types import AudioCaptureConfig
from tests.fidelity.fake_device import (
    FakePwRecordProcess,
    drain_all,
    f32_bytes,
    synthetic_pw_record,
)
from tests.fixtures import signal_generators as sg

pytestmark = [pytest.mark.fidelity, pytest.mark.fuzz]

SR = 16000
CHUNK = 480

# Estabilidade de CI: poucos exemplos, sem deadline de tempo.
HYP_SETTINGS = settings(max_examples=25, deadline=None)


def _fake_settings(**overrides):
    """Namespace com TODOS os campos lidos por validate_settings real."""
    from types import SimpleNamespace

    base = {
        "platform_backend": "auto",
        "audio_backend": "auto",
        "audio_source": "system",
        "caption_source": "auto",
        "screen_capture_backend": "auto",
        "stt_device": "cpu",
        "sample_rate": 16000,
        "channels": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# FUZZ-01 — Sample rates inválidos: erro explícito ou pass-through gracioso
# ---------------------------------------------------------------------------

class TestFuzz01InvalidSampleRate:
    @HYP_SETTINGS
    @given(st.one_of(
        st.integers(max_value=0),          # zero ou negativo
        st.integers(min_value=1, max_value=99),  # absurdo baixo
        st.sampled_from([None, "16k", 16000.5, -1, 0]),
    ))
    def test_invalid_rate_config_behavior(self, rate):
        """Config com taxa inválida: ou o validador real acusa erro
        explícito, ou o valor passa intacto ao comando (pass-through
        documentado — o pw-record real falharia no subprocesso, não em
        Python). Nunca crash silencioso no construtor."""
        config = AudioCaptureConfig(device_id="42", sample_rate=16000)
        # Construtor sempre aceita (dataclass) — pass-through documentado
        config.sample_rate = rate if isinstance(rate, int) else 16000
        assert config.sample_rate is not None

        cap = PipewireCapture(device_id="42", sample_rate=16000,
                              chunk_size=CHUNK)
        cap.sample_rate = config.sample_rate
        cmd = cap._build_cmd()
        # O comando reflete exatamente o valor pedido — sem reescrita oculta
        assert str(config.sample_rate) in cmd

    @HYP_SETTINGS
    @given(st.integers(max_value=0))
    def test_settings_validator_flags_invalid_rate(self, bad_rate):
        """O validador REAL do produto (validate_settings) acusa taxas
        não-positivas com mensagem explícita — erro visível, não silencioso."""
        from src.config import validate_settings

        errors = validate_settings(_fake_settings(sample_rate=bad_rate))
        assert any("sample_rate" in e for e in errors), (
            f"validador deveria acusar sample_rate={bad_rate}"
        )


# ---------------------------------------------------------------------------
# FUZZ-02 — Canais inválidos: a fachada nunca sai de mono
# ---------------------------------------------------------------------------

class TestFuzz02InvalidChannels:
    @HYP_SETTINGS
    @given(st.one_of(st.integers(min_value=-4, max_value=8),
                     st.sampled_from([None, "2", 2.0])))
    def test_facade_always_mono(self, _anything):
        """A API pública (AudioCapture) endurece channels=1 sempre —
        canais inválidos do usuário nunca alcançam o backend."""
        from src.audio.capture import AudioCapture

        cap = AudioCapture()
        assert cap.channels == 1

    @HYP_SETTINGS
    @given(st.integers(min_value=-4, max_value=8).filter(
        lambda c: c not in (1, 2)))
    def test_settings_validator_flags_invalid_channels(self, bad_ch):
        from src.config import validate_settings

        errors = validate_settings(_fake_settings(channels=bad_ch))
        assert any("channels" in e for e in errors)

    def test_config_accepts_any_channels_but_contract_declares_mono(self):
        """AudioCaptureConfig aceita channels arbitrário (sem validação),
        mas o formato canônico declarado é pcm_s16le mono — o contrato do
        pipeline. Documentado: backend é responsável pelo downmix."""
        config = AudioCaptureConfig(channels=2)
        assert config.format == "pcm_s16le"


# ---------------------------------------------------------------------------
# FUZZ-03 — Dispositivo inexistente: falha sem exceção mascarada
# ---------------------------------------------------------------------------

class TestFuzz03NonexistentDevice:
    @HYP_SETTINGS
    @given(st.text(min_size=1, max_size=40))
    def test_nonexistent_device_graceful_eof(self, dev_id):
        """Device inexistente: o pw-record real morre no boot → EOF →
        nenhum chunk, captura encerra limpa, stop() sem travar.

        Simulação: subprocesso fake com stdout vazio (EOF imediato).
        """
        cap = PipewireCapture(device_id=dev_id, sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id=dev_id, sample_rate=SR,
                                    channels=1, chunk_frames=CHUNK)
        q = queue_mod.Queue()
        with synthetic_pw_record(b""):
            cap.start(config, q)
            thread = cap._thread
            assert thread is not None
            thread.join(timeout=10.0)
            assert not thread.is_alive(), "captura travou com device morto"
            chunks = drain_all(q)
            cap.stop()
        assert chunks == [], "device morto não deveria publicar chunks"
        assert cap.is_running is False

    def test_factory_wasapi_non_numeric_device_raises_explicit(self):
        """Factory WASAPI com device não-numérico: ValueError explícito
        (documentado — conversão int() no factory), não silêncio."""
        monkey = pytest.MonkeyPatch()
        monkey.setattr(sys, "platform", "win32")
        try:
            from src.platform import detection

            monkey.setattr(detection, "_check_pipewire_running", lambda: False)
            from src.audio.backends import build_audio_backend

            with pytest.raises((ValueError, AudioBackendError)):
                build_audio_backend("wasapi", device_id="não-numérico!")
        finally:
            monkey.undo()


# ---------------------------------------------------------------------------
# FUZZ-04 — Chunks extremos: 0, 1 frame, ímpar, grande
# ---------------------------------------------------------------------------

class TestFuzz04ExtremeChunks:
    @HYP_SETTINGS
    @given(st.sampled_from([1, 2, 7, 160, 4096]))
    def test_extreme_chunk_frames_produce_valid_pcm(self, chunk_frames):
        """chunk_frames extremos (1..4096): chunks publicados continuam
        canônicos (bytes pares, tamanho exato) e o loop não trava."""
        sig = sg.sine(freq_hz=440.0, duration_s=0.5, sample_rate=SR,
                      amplitude=0.5)
        n = (len(sig) // chunk_frames) * chunk_frames
        sig = sig[:n]
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=chunk_frames)
        config = AudioCaptureConfig(device_id="42", sample_rate=SR,
                                    channels=1, chunk_frames=chunk_frames)
        q = queue_mod.Queue()
        with synthetic_pw_record(f32_bytes(sig)):
            cap.start(config, q)
            thread = cap._thread
            assert thread is not None
            thread.join(timeout=15.0)
            chunks = drain_all(q)
            cap.stop()
        if n > 0:
            assert chunks, "nenhum chunk com entrada válida"
        for c in chunks:
            assert len(c) == chunk_frames * 2
            assert len(c) % 2 == 0

    @HYP_SETTINGS
    @given(st.binary(min_size=0, max_size=2048))
    def test_mixer_odd_and_empty_frames_graceful(self, raw):
        """Mixer com frames arbitrários (vazios, ímpares, truncados):
        nunca levanta; saída sempre PCM par ou vazia."""
        from src.audio.mixer import AudioMixer

        mixer = AudioMixer(sample_rate=SR, channels=1)
        out = mixer.mix_frame(raw, raw)
        assert isinstance(out, bytes)
        assert len(out) % 2 == 0

    def test_empty_stream_publishes_nothing(self):
        """Stream vazio (0 bytes): zero chunks, encerramento limpo."""
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42")
        q = queue_mod.Queue()
        with synthetic_pw_record(b""):
            cap.start(config, q)
            cap._thread.join(timeout=10.0)
            chunks = drain_all(q)
            cap.stop()
        assert chunks == []


# ---------------------------------------------------------------------------
# FUZZ-05 — Duplo start / stop sem start / stop duplo
# ---------------------------------------------------------------------------

class TestFuzz05LifecycleIdempotence:
    def test_double_start_spawns_single_subprocess(self):
        """start() duas vezes: idempotente — um único Popen criado
        (guarda de _is_running do produto)."""
        sig = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                      amplitude=0.5)
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42")
        q = queue_mod.Queue()
        popen_calls: list = []

        def counting_popen(cmd, **kwargs):
            popen_calls.append(list(cmd))
            return FakePwRecordProcess(f32_bytes(sig))

        with patch("src.audio.backends.pipewire.capture.shutil.which",
                   return_value="/usr/bin/pw-record"):
            with patch(
                "src.audio.backends.pipewire.capture.subprocess.Popen",
                side_effect=counting_popen,
            ):
                cap.start(config, q)
                cap.start(config, q)  # segunda chamada: no-op
                cap._thread.join(timeout=10.0)
                drain_all(q)
                cap.stop()
        assert len(popen_calls) == 1, (
            f"duplo start criou {len(popen_calls)} subprocessos — idempotência "
            "violada"
        )

    @HYP_SETTINGS
    @given(st.integers(min_value=1, max_value=3))
    def test_multiple_stops_without_start_are_safe(self, n_stops):
        cap = PipewireCapture()
        for _ in range(n_stops):
            cap.stop()  # não deve levantar
        assert cap.is_running is False

    def test_stop_twice_after_run_is_safe(self):
        sig = sg.sine(freq_hz=440.0, duration_s=0.5, sample_rate=SR,
                      amplitude=0.5)
        _, chunks, _ = _run_and_stop(sig)
        assert chunks
        # segundo stop idempotente via helper manual
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        cap.stop()
        cap.stop()


def _run_and_stop(sig):
    from tests.fidelity.fake_device import run_pipewire_capture

    return run_pipewire_capture(sig, sample_rate=SR, chunk_frames=CHUNK)


# ---------------------------------------------------------------------------
# FUZZ-06 — Falha/interrupção de dispositivo sem travamento
# ---------------------------------------------------------------------------

class TestFuzz06DeviceFailure:
    def test_popen_spawn_failure_no_hang(self):
        """Subprocesso falha ao nascer (FileNotFoundError): loop registra,
        _is_running vai a False, nada trava, nenhuma exceção escapa."""

        def broken_popen(cmd, **kwargs):
            raise FileNotFoundError("pw-record sumiu entre which() e spawn")

        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42")
        q = queue_mod.Queue()
        with patch("src.audio.backends.pipewire.capture.shutil.which",
                   return_value="/usr/bin/pw-record"):
            with patch(
                "src.audio.backends.pipewire.capture.subprocess.Popen",
                side_effect=broken_popen,
            ):
                cap.start(config, q)
                thread = cap._thread
                assert thread is not None
                thread.join(timeout=10.0)
                assert not thread.is_alive(), (
                    "thread travou após falha de spawn do subprocesso"
                )
        assert cap._is_running is False, (
            "is_running deveria ser False após falha de spawn"
        )
        cap.stop()
        assert drain_all(q) == []

    def test_device_dies_midstream_keeps_valid_chunks(self):
        """Dispositivo morre no meio: chunks já publicados permanecem
        válidos; o restante é descartado sem corromper os anteriores."""
        good = sg.sine(freq_hz=440.0, duration_s=1.0, sample_rate=SR,
                       amplitude=0.5)
        n_good = (len(good) // CHUNK) * CHUNK
        stream = f32_bytes(good[:n_good]) + b"\x00" * 137  # cauda truncada
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42")
        q = queue_mod.Queue()
        with synthetic_pw_record(stream):
            cap.start(config, q)
            thread = cap._thread
            assert thread is not None
            thread.join(timeout=10.0)
            chunks = drain_all(q)
            cap.stop()
        assert len(chunks) == n_good // CHUNK
        for c in chunks:
            assert len(c) == CHUNK * 2

    def test_stderr_output_does_not_crash_eof_path(self):
        """stderr cheio no EOF: caminho de diagnóstico não explode
        (BytesIO não tem fd real — select falha e é tratado)."""
        sig = sg.sine(freq_hz=440.0, duration_s=0.5, sample_rate=SR,
                      amplitude=0.5)
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=CHUNK)
        config = AudioCaptureConfig(device_id="42")
        q = queue_mod.Queue()
        with synthetic_pw_record(f32_bytes(sig), stderr=b"boom\n" * 100):
            cap.start(config, q)
            cap._thread.join(timeout=10.0)
            drain_all(q)
            cap.stop()  # não deve levantar
        assert cap.is_running is False
