"""CONF-01..CONF-04 — Conformance dos backends com o contrato real.

Classificação honesta: integração com código real (offline) para
PipewireCapture (protocolo, cmd, chunks via device sintético) e
verificação estrutural para WasapiLoopbackCapture (classe real,
sem PyAudio/hardware no ambiente).

Encontrado durante a análise (documentado em DECISOES.md D-008):
``WasapiLoopbackCapture.start()`` sem PyAudio instalado deixa a exceção
morrer na thread interna sem propagar ao chamador — comportamento
registrado como risco, não alterado nesta PR (fora do escopo de teste).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.audio.backends import AudioBackendError, build_audio_backend
from src.audio.backends.pipewire.capture import PipewireCapture
from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
from src.platform.types import (
    AudioCaptureBackend,
    AudioCaptureConfig,
    AudioChunk,
    AudioDevice,
)
from tests.fidelity.fake_device import (
    drain_all,
    f32_bytes,
    synthetic_pw_record,
)
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
CHUNK = 480


# ---------------------------------------------------------------------------
# CONF-01 — Aderência real ao Protocol AudioCaptureBackend
# ---------------------------------------------------------------------------

class TestConf01ProtocolAdherence:
    def test_pipewire_capture_satisfies_protocol(self):
        """PipewireCapture implementa a interface completa do Protocol."""
        cap = PipewireCapture()
        assert isinstance(cap, AudioCaptureBackend), (
            "PipewireCapture não adere ao Protocol AudioCaptureBackend"
        )

    def test_wasapi_capture_satisfies_protocol(self):
        cap = WasapiLoopbackCapture()
        assert isinstance(cap, AudioCaptureBackend), (
            "WasapiLoopbackCapture não adere ao Protocol AudioCaptureBackend"
        )

    @pytest.mark.parametrize("backend_cls", [PipewireCapture,
                                             WasapiLoopbackCapture])
    def test_protocol_surface_signatures(self, backend_cls):
        """Métodos do contrato existem com assinatura utilizável."""
        cap = backend_cls()
        assert callable(getattr(cap, "list_devices"))
        assert callable(getattr(cap, "start"))
        assert callable(getattr(cap, "stop"))
        assert isinstance(cap.is_running, bool)

    def test_list_devices_returns_audio_device_list(self):
        """list_devices retorna list[AudioDevice] (tipos do contrato)."""
        for cap in (PipewireCapture(), WasapiLoopbackCapture()):
            devices = cap.list_devices()
            assert isinstance(devices, list)
            for d in devices:
                assert isinstance(d, AudioDevice)

    def test_factory_returns_protocol_instance(self, monkeypatch):
        """A fábrica devolve instância que satisfaz o Protocol."""
        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection

        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        backend = build_audio_backend("pipewire")
        assert isinstance(backend, AudioCaptureBackend)


# ---------------------------------------------------------------------------
# CONF-02 — Chunks publicados em formato canônico (PCM s16le)
# ---------------------------------------------------------------------------

class TestConf02CanonicalChunkFormat:
    @pytest.mark.parametrize("chunk_frames", [160, 480, 960])
    def test_chunks_canonical_through_real_loop(self, chunk_frames):
        """Chunks do loop real: bytes pares, tamanho exato, int16 válido,
        equivalentes em duração ao stream de entrada."""
        sig = sg.speech_like(duration_s=1.5, sample_rate=SR, seed=7,
                             amplitude=0.4)
        n = (len(sig) // chunk_frames) * chunk_frames
        sig = sig[:n]
        cap = PipewireCapture(device_id="42", sample_rate=SR,
                              chunk_size=chunk_frames)
        config = AudioCaptureConfig(device_id="42", sample_rate=SR,
                                    channels=1, chunk_frames=chunk_frames)
        import queue as queue_mod

        q = queue_mod.Queue()
        with synthetic_pw_record(f32_bytes(sig)):
            cap.start(config, q)
            thread = cap._thread
            assert thread is not None
            thread.join(timeout=15.0)
            chunks = drain_all(q)
            cap.stop()

        expected_frames = n // chunk_frames
        assert len(chunks) == expected_frames
        for c in chunks:
            assert len(c) == chunk_frames * 2
            assert len(c) % 2 == 0
            arr = np.frombuffer(c, dtype=np.int16)
            assert arr.dtype.itemsize == 2
            # PCM s16le: little-endian — decodificação consistente
            assert arr.size == chunk_frames

    def test_chunk_equivalence_across_sizes(self):
        """Equivalência de formato: stream concatenado idêntico para
        chunk_frames diferentes (mesma entrada, mesmo conteúdo)."""
        sig = sg.sine(freq_hz=440.0, duration_s=1.2, sample_rate=SR,
                      amplitude=0.5)
        n = (len(sig) // 960) * 960
        sig = sig[:n]
        collected = {}
        for cf in (160, 480, 960):
            cap = PipewireCapture(device_id="42", sample_rate=SR,
                                  chunk_size=cf)
            config = AudioCaptureConfig(device_id="42", sample_rate=SR,
                                        channels=1, chunk_frames=cf)
            import queue as queue_mod

            q = queue_mod.Queue()
            with synthetic_pw_record(f32_bytes(sig)):
                cap.start(config, q)
                thread = cap._thread
                assert thread is not None
                thread.join(timeout=15.0)
                chunks = drain_all(q)
                cap.stop()
            collected[cf] = b"".join(chunks)
        assert collected[160] == collected[480] == collected[960], (
            "conteúdo publicado difere entre tamanhos de chunk — "
            "violação de equivalência de formato"
        )


# ---------------------------------------------------------------------------
# CONF-03 — Erros explícitos na ausência de recurso
# ---------------------------------------------------------------------------

class TestConf03ExplicitErrors:
    def test_start_without_pw_record_raises_runtime_error(self):
        """Sem pw-record instalado: RuntimeError explícito e actionable."""
        cap = PipewireCapture()
        config = AudioCaptureConfig(device_id="42")
        with patch(
            "src.audio.backends.pipewire.capture.shutil.which",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="pw-record não encontrado"):
                cap.start(config, MagicMock())

    def test_factory_unknown_backend_raises_explicit(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(AudioBackendError):
            build_audio_backend("alsa")

    def test_factory_unavailable_platform_raises_explicit(self, monkeypatch):
        """Pedir wasapi em Linux: erro explícito (não silêncio falso)."""
        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection

        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        with pytest.raises(AudioBackendError):
            build_audio_backend("wasapi")


# ---------------------------------------------------------------------------
# CONF-04 — Fachada AudioCapture retrocompatível
# ---------------------------------------------------------------------------

class TestConf04FacadeRetrocompat:
    def test_facade_end_to_end_publishes_canonical_chunks(self, monkeypatch):
        """Fachada → fábrica → backend real → chunks canônicos (offline).

        Exercita o caminho completo da API pública com device sintético:
        a config construída pela fachada chega intacta ao backend.
        """
        from src.audio.capture import AudioCapture

        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection

        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)

        sig = sg.sine(freq_hz=1000.0, duration_s=1.5, sample_rate=SR,
                      amplitude=0.5)
        n = (len(sig) // CHUNK) * CHUNK
        sig = sig[:n]

        import queue as queue_mod

        q = queue_mod.Queue()
        facade = AudioCapture(device_index="42", sample_rate=SR,
                              chunk_size=CHUNK)
        with synthetic_pw_record(f32_bytes(sig)):
            facade.start(q)
            backend = facade._backend
            assert backend is not None
            thread = getattr(backend, "_thread", None)
            assert thread is not None
            thread.join(timeout=15.0)
            chunks = drain_all(q)
            facade.stop()

        assert len(chunks) == n // CHUNK
        assert all(len(c) == CHUNK * 2 for c in chunks)
        assert facade.is_running is False

    def test_facade_list_devices_dict_keys(self, monkeypatch):
        """Formato legado dos dicts de list_devices preservado."""
        from src.audio.capture import AudioCapture

        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection

        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        cap = AudioCapture()
        devices = cap.list_devices()
        for d in devices:
            for key in ("index", "name", "channels", "rate", "is_loopback"):
                assert key in d, f"chave legada {key!r} ausente"

    def test_facade_device_index_accepts_int_and_str(self):
        from src.audio.capture import AudioCapture

        assert AudioCapture(device_index=42).device_index == 42
        assert AudioCapture(device_index="42").device_index == "42"

    def test_facade_no_backend_start_is_graceful(self):
        """Sem backend disponível: start() loga e não explode (contrato
        documentado da fachada — backend nulo)."""
        from src.audio.capture import AudioCapture

        cap = AudioCapture(backend="inexistente-nao-usable")
        cap.start(MagicMock())  # não deve levantar
        assert cap.is_running is False
        cap.stop()

    def test_audio_chunk_dataclass_contract(self):
        """AudioChunk: campos canônicos com defaults corretos."""
        chunk = AudioChunk(data=b"\x01\x02")
        assert chunk.sample_rate == SR
        assert chunk.channels == 1
        assert chunk.timestamp == 0.0
        assert isinstance(chunk.data, bytes)


# ---------------------------------------------------------------------------
# Achado documentado — WASAPI sem PyAudio (ver DECISOES.md D-008)
# ---------------------------------------------------------------------------

class TestWasapiKnownLimitation:
    @pytest.mark.filterwarnings(
        "ignore::pytest.PytestUnhandledThreadExceptionWarning"
    )
    def test_wasapi_start_without_pyaudio_documented_behavior(self):
        """REGISTRO DE COMPORTAMENTO (não é validação de sucesso):

        Sem PyAudio, start() da WasapiLoopbackCapture lança a exceção
        dentro da thread interna — o chamador não recebe erro explícito
        e is_running permanece True até stop(). Documentado como risco
        em DECISOES.md D-008; correção fica para PR dedicada (exige
        ambiente Windows para validar).
        """
        cap = WasapiLoopbackCapture()
        try:
            with patch.dict(sys.modules, {"pyaudio": None}):
                cap.start(AudioCaptureConfig(), MagicMock())
                # thread interna morre com ImportError sem propagar:
                thread = cap._thread
                assert thread is not None
                thread.join(timeout=5.0)
                assert not thread.is_alive(), (
                    "thread WASAPI deveria terminar (ImportError no import "
                    "do pyaudio dentro do loop)"
                )
        finally:
            cap.stop()
            assert cap.is_running is False
