"""Testes para os backends de áudio (WasapiLoopbackCapture e PipewireCapture).

Todos os testes usam mocks — não exigem hardware real, PyAudio instalado,
ou PipeWire rodando.
"""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.platform.types import AudioCaptureConfig


# ---------------------------------------------------------------------------
# WasapiLoopbackCapture
# ---------------------------------------------------------------------------

class TestWasapiLoopbackCapture:
    def test_list_devices_no_pyaudio(self):
        """Sem PyAudio instalado, list_devices retorna [] (não quebra)."""
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        cap = WasapiLoopbackCapture()
        # PyAudio não está instalado neste ambiente de teste Linux.
        devices = cap.list_devices()
        assert isinstance(devices, list)
        assert devices == []

    def test_list_devices_with_mock_pyaudio(self):
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        cap = WasapiLoopbackCapture()

        # Mock do módulo pyaudio
        mock_pa = MagicMock()
        mock_pa.paWASAPI = 1
        mock_pa.PyAudio.return_value.get_host_api_info_by_type.return_value = {
            "index": 1
        }
        mock_pa.PyAudio.return_value.get_device_count.return_value = 2
        mock_pa.PyAudio.return_value.get_device_info_by_index.side_effect = [
            {"hostApi": 1, "name": "Mic", "maxInputChannels": 1, "defaultSampleRate": 16000},
            {"hostApi": 1, "name": "Speaker (Loopback)", "maxInputChannels": 2, "defaultSampleRate": 44100},
        ]
        mock_pa.PyAudio.return_value.terminate.return_value = None

        with patch.dict(sys.modules, {"pyaudio": mock_pa}):
            devices = cap.list_devices()

        assert len(devices) == 2
        assert devices[0].name == "Mic"
        assert devices[0].kind == "input"
        assert devices[1].name == "Speaker (Loopback)"
        assert devices[1].kind == "output"  # loopback = output
        assert devices[1].backend == "wasapi"

    def test_is_running_initial_false(self):
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        cap = WasapiLoopbackCapture()
        assert cap.is_running is False

    def test_stop_without_start_idempotent(self):
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        cap = WasapiLoopbackCapture()
        cap.stop()  # não deve lançar exceção


# ---------------------------------------------------------------------------
# PipewireCapture
# ---------------------------------------------------------------------------

class TestPipewireCapture:
    def test_list_devices_returns_list(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture()
        # pactl não está disponível no ambiente de teste; esperamos [].
        devices = cap.list_devices()
        assert isinstance(devices, list)

    def test_list_devices_with_mock_pactl(self):
        from src.audio.backends.pipewire import devices as devmod

        # Mock da saída do pactl list sources
        sample_output = """Source #42
\tState: RUNNING
\tName: alsa_output.pci-0000_00_1b.0.analog-stereo.monitor
\tDescription: Monitor of Built-in Audio Analog Stereo
\tSample Specification: s16le 2ch 44100Hz

Source #43
\tState: SUSPENDED
\tName: alsa_input.pci-0000_00_1b.0.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tSample Specification: s16le 2ch 44100Hz
"""
        with patch.object(devmod, "_run_pactl_list", return_value=sample_output):
            with patch.object(devmod, "_have_pactl", return_value=True):
                devices = devmod.list_pipewire_devices()

        assert len(devices) == 2
        kinds = [d.kind for d in devices]
        assert "monitor" in kinds
        assert "input" in kinds
        assert all(d.backend == "pipewire" for d in devices)

    def test_run_pactl_list_forces_c_locale(self):
        """Regressão: pactl deve rodar com locale C para saída estável em inglês.

        Em desktops Fedora com locale pt_BR, o pactl traduz os cabeçalhos
        ("Fonte #N", "Estado:") e o parser de dispositivos quebrava,
        retornando [] mesmo com microfone e monitor presentes.
        """
        from src.audio.backends.pipewire import devices as devmod

        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            class _R:
                returncode = 0
                stdout = "Source #1\n\tState: RUNNING\n"
                stderr = ""
            return _R()

        with patch.object(subprocess, "run", side_effect=fake_run):
            with patch.object(devmod, "_have_pactl", return_value=True):
                out = devmod._run_pactl_list("sources")

        assert captured["cmd"] == ["pactl", "list", "sources"]
        env = captured["env"]
        assert env is not None
        assert env["LC_ALL"] == "C"
        assert env["LANG"] == "C"
        assert out.startswith("Source #1"), (
            f"Saída do pactl deveria estar em inglês, mas recebeu: {out!r}"
        )

    def test_is_running_initial_false(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture()
        assert cap.is_running is False

    def test_stop_without_start_idempotent(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture()
        cap.stop()  # não deve lançar

    def test_pump_stdout_sanitizes_nan_inf(self):
        """Regressão: chunk f32 com NaN/Inf (fonte monitor idle) vira 0.

        Em Fedora, o monitor do sink idle entrega amostras NaN que
        quebravam o cast para int16 com RuntimeWarning e produziam
        valores indefinidos no PCM.
        """
        import io
        import queue

        import numpy as np

        from src.audio.backends.pipewire.capture import PipewireCapture

        cap = PipewireCapture(device_id="50", sample_rate=16000, chunk_size=480)
        q: queue.Queue = queue.Queue()
        cap._queue = q
        cap._is_running = True

        arr = np.zeros(480, dtype=np.float32)
        arr[0] = np.nan
        arr[1] = np.inf
        arr[2] = -np.inf
        arr[3] = 0.5
        stream = io.BytesIO(arr.tobytes())

        cap._pump_stdout(stream)
        cap._is_running = False

        assert q.qsize() == 1, "Nenhum chunk publicado na fila"
        out = np.frombuffer(q.get(), dtype=np.int16)
        assert out[0] == 0, "NaN deveria virar 0"
        assert out[1] == 0, "+Inf deveria virar 0"
        assert out[2] == 0, "-Inf deveria virar 0"
        assert abs(int(out[3])) > 0, "0.5 deveria produzir sample não-zero"

    def test_drain_queue_empties_pending_data(self):
        """Regressão: _drain_queue libera o feeder do multiprocessing.Queue.

        Sem a drenagem em stop(), dados não lidos deixavam o feeder thread
        bloqueado num pipe cheio e o processo Python não encerrava após
        start/stop sem leitura (ex.: E2E-08/E2E-13 e o próprio app).
        """
        import queue

        from src.audio.backends.pipewire.capture import PipewireCapture

        cap = PipewireCapture(device_id="50", sample_rate=16000, chunk_size=480)
        q: queue.Queue = queue.Queue()
        for _ in range(50):
            q.put(b"\x00" * 960)
        cap._queue = q
        cap._drain_queue()
        assert q.empty(), "Drenagem deveria esvaziar a fila"

    def test_start_without_pw_record_raises(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture()
        with patch("src.audio.backends.pipewire.capture.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="pw-record não encontrado"):
                cap.start(
                    AudioCaptureConfig(device_id="42"),
                    output_queue=MagicMock(),
                )

    def test_build_cmd_includes_target(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture(device_id="42", sample_rate=16000, chunk_size=480)
        cmd = cap._build_cmd()
        assert cmd[0] == "pw-record"
        assert "--format" in cmd and "f32" in cmd
        assert "--rate" in cmd and "16000" in cmd
        assert "--channels" in cmd and "1" in cmd
        assert "--target" in cmd and "42" in cmd
        assert cmd[-1] == "-"  # stdout

    def test_build_cmd_no_target_when_device_none(self):
        from src.audio.backends.pipewire.capture import PipewireCapture
        cap = PipewireCapture(device_id=None)
        cmd = cap._build_cmd()
        assert "--target" not in cmd


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestAudioBackendFactory:
    def test_build_wasapi_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.audio.backends import build_audio_backend
        backend = build_audio_backend("auto")
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        assert isinstance(backend, WasapiLoopbackCapture)

    def test_build_pipewire_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        from src.audio.backends import build_audio_backend
        backend = build_audio_backend("auto")
        from src.audio.backends.pipewire.capture import PipewireCapture
        assert isinstance(backend, PipewireCapture)

    def test_build_invalid_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.audio.backends import build_audio_backend, AudioBackendError
        with pytest.raises(AudioBackendError):
            build_audio_backend("alsa")

    def test_build_pipewire_explicit_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        from src.audio.backends import build_audio_backend
        backend = build_audio_backend("pipewire")
        from src.audio.backends.pipewire.capture import PipewireCapture
        assert isinstance(backend, PipewireCapture)


# ---------------------------------------------------------------------------
# AudioCapture facade (retrocompatibilidade)
# ---------------------------------------------------------------------------

class TestAudioCaptureFacade:
    def test_list_devices_returns_dicts(self, monkeypatch):
        """A fachada deve retornar dicts com chaves 'index', 'name' (compat)."""
        monkeypatch.setattr(sys, "platform", "linux")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        from src.audio.capture import AudioCapture
        cap = AudioCapture()
        devices = cap.list_devices()
        for d in devices:
            assert "index" in d
            assert "name" in d
            assert "channels" in d
            assert "rate" in d

    def test_device_index_accepts_str_or_int(self):
        from src.audio.capture import AudioCapture
        cap1 = AudioCapture(device_index=42)
        cap2 = AudioCapture(device_index="42")
        assert cap1.device_index == 42
        assert cap2.device_index == "42"

    def test_backend_field_default_auto(self):
        from src.audio.capture import AudioCapture
        cap = AudioCapture()
        assert cap._backend_name == "auto"
