"""Testes de integração REAIS do backend PipeWire.

Estes testes exigem:
- PipeWire rodando (``systemctl --user status pipewire``)
- ``pactl`` disponível
- ``pw-record`` disponível
- Uma fonte de áudio real (microfone ou monitor)

NÃO usam mocks. NÃO baixam modelos. NÃO exigem rede.

Marcadores:
    @pytest.mark.integration
    @pytest.mark.requires_pipewire

Rodar:
    pytest -q -m "integration and requires_pipewire"

Pula automaticamente se PipeWire não estiver disponível.
"""
from __future__ import annotations

import multiprocessing
import os
import time

import pytest

from tests.integration.conftest import (
    count_pw_record_processes,
    fixture_sha256,
    generate_sine_wave_pcm16,
    is_silence,
    kill_orphan_pw_record,
    require_pactl,
    require_pipewire,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_pipewire,
]


class TestPipewireBackendReal:
    """Validação real do backend PipeWire em Fedora desktop."""

    def setup_method(self):
        """Pula se PipeWire não estiver rodando."""
        require_pipewire()
        require_pactl()
        # Snapshot do número de pw-record antes do teste
        self._initial_pw_record = count_pw_record_processes()

    def teardown_method(self):
        """Cleanup: mata pw-record órfão se houver."""
        leaked = count_pw_record_processes() - self._initial_pw_record
        if leaked > 0:
            killed = kill_orphan_pw_record()
            # Não falha o teste aqui — apenas registra para diagnóstico.
            # O teste E2E-08 valida explicitamente ausência de órfãos.

    # ------------------------------------------------------------------
    # E2E-03: Detecção PipeWire
    # ------------------------------------------------------------------

    def test_e2e_03_pipewire_detection(self):
        """E2E-03: O diagnóstico identifica PipeWire e lista fontes reais."""
        from src.audio.backends.pipewire.devices import list_pipewire_devices

        devices = list_pipewire_devices()
        assert isinstance(devices, list)
        # Em um desktop Fedora funcional, deve haver ao menos 1 fonte
        # (microfone interno ou monitor do sink padrão).
        assert len(devices) >= 1, (
            "Nenhuma fonte de áudio PipeWire encontrada. "
            "Verifique se há microfone ou sink ativo."
        )
        # Pelo menos um dispositivo deve ter nome não vazio
        for d in devices:
            assert d.name, f"Dispositivo {d.id} sem nome"
            assert d.backend == "pipewire"
            assert d.kind in ("input", "monitor", "output")

    def test_e2e_03_pipewire_socket_exists(self):
        """Confirma que o socket PipeWire está ativo."""
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
        socket_path = os.path.join(runtime_dir, "pipewire-0") if runtime_dir else ""
        assert socket_path and os.path.exists(socket_path), (
            f"Socket PipeWire não encontrado em {socket_path!r}"
        )

    # ------------------------------------------------------------------
    # E2E-04: Detecção de microfone
    # ------------------------------------------------------------------

    def test_e2e_04_microphone_detection(self):
        """E2E-04: Backend lista ao menos um microfone ou fonte de entrada."""
        from src.audio.backends.pipewire.devices import list_pipewire_devices

        devices = list_pipewire_devices()
        inputs = [d for d in devices if d.kind == "input"]
        if not inputs:
            pytest.skip(
                "Nenhum microfone detectado — conecte um microfone físico "
                "ou crie uma fonte virtual (pactl load-module module-null-sink)"
            )
        assert len(inputs) >= 1
        # Valida estrutura
        mic = inputs[0]
        assert mic.id
        assert mic.name
        assert mic.channels >= 1
        assert mic.sample_rate > 0

    # ------------------------------------------------------------------
    # E2E-05: Detecção de áudio do sistema (monitor)
    # ------------------------------------------------------------------

    def test_e2e_05_monitor_detection(self):
        """E2E-05: Backend identifica uma fonte monitor (áudio do sistema)."""
        from src.audio.backends.pipewire.devices import list_pipewire_devices

        devices = list_pipewire_devices()
        monitors = [d for d in devices if d.kind == "monitor"]
        if not monitors:
            pytest.skip(
                "Nenhuma fonte monitor encontrada. "
                "Toque qualquer som (música/vídeo) para criar o monitor "
                "do sink ativo."
            )
        assert len(monitors) >= 1
        mon = monitors[0]
        assert mon.id
        assert "monitor" in mon.name.lower() or "sistema" in mon.name.lower()

    # ------------------------------------------------------------------
    # E2E-06: Captura de microfone real
    # ------------------------------------------------------------------

    def test_e2e_06_microphone_capture(self):
        """E2E-06: Captura 2s de microfone e valida chunks não silenciosos.

        Requer microfone físico conectado e permissão de acesso.
        Se não houver microfone, o teste pula (não falha).
        """
        from src.audio.backends.pipewire.capture import PipewireCapture
        from src.audio.backends.pipewire.devices import list_pipewire_devices
        from src.platform.types import AudioCaptureConfig

        devices = list_pipewire_devices()
        inputs = [d for d in devices if d.kind == "input"]
        if not inputs:
            pytest.skip("Sem microfone — conecte um dispositivo de entrada")

        mic = inputs[0]
        queue: multiprocessing.Queue = multiprocessing.Queue()
        cap = PipewireCapture(device_id=mic.id, sample_rate=16000, chunk_size=480)

        try:
            cap.start(
                AudioCaptureConfig(device_id=mic.id, sample_rate=16000, chunk_frames=480),
                output_queue=queue,
            )
            assert cap.is_running, "Backend não entrou em estado running"
            assert count_pw_record_processes() > self._initial_pw_record, (
                "Processo pw-record não foi iniciado"
            )

            # Coleta chunks por 2 segundos
            chunks = []
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    chunk = queue.get(timeout=0.5)
                    chunks.append(chunk)
                except Exception:
                    continue

            assert len(chunks) >= 1, "Nenhum chunk recebido em 2s"
            # Valida formato: cada chunk deve ter tamanho múltiplo de 2 (PCM s16le)
            for c in chunks:
                assert len(c) > 0
                assert len(c) % 2 == 0, f"Chunk com tamanho ímpar: {len(c)}"
            # Pelo menos um chunk não deve ser silêncio total
            # (microfone pode estar mudo; neste caso, skip em vez de fail)
            non_silent = [c for c in chunks if not is_silence(c)]
            if not non_silent:
                pytest.skip(
                    "Microfone capturou apenas silêncio. "
                    "Faça barulho perto do microfone ou aumente o ganho."
                )
        finally:
            cap.stop()
            # Confirma que parou
            time.sleep(0.3)
            assert not cap.is_running

    # ------------------------------------------------------------------
    # E2E-07: Captura do sistema (monitor)
    # ------------------------------------------------------------------

    def test_e2e_07_system_audio_capture(self):
        """E2E-07: Captura 3s da fonte monitor e valida chunks não silenciosos.

        Requer áudio sendo reproduzido no sistema (navegador, player, etc.).
        """
        from src.audio.backends.pipewire.capture import PipewireCapture
        from src.audio.backends.pipewire.devices import list_pipewire_devices
        from src.platform.types import AudioCaptureConfig

        devices = list_pipewire_devices()
        monitors = [d for d in devices if d.kind == "monitor"]
        if not monitors:
            pytest.skip("Sem fonte monitor — toque um áudio no sistema")

        mon = monitors[0]
        queue: multiprocessing.Queue = multiprocessing.Queue()
        cap = PipewireCapture(device_id=mon.id, sample_rate=16000, chunk_size=480)

        try:
            cap.start(
                AudioCaptureConfig(device_id=mon.id, sample_rate=16000, chunk_frames=480),
                output_queue=queue,
            )
            assert cap.is_running

            chunks = []
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                try:
                    chunk = queue.get(timeout=0.5)
                    chunks.append(chunk)
                except Exception:
                    continue

            assert len(chunks) >= 1, "Nenhum chunk recebido do monitor"
            non_silent = [c for c in chunks if not is_silence(c)]
            if not non_silent:
                pytest.skip(
                    "Monitor capturou apenas silêncio. "
                    "Toque um áudio no sistema durante o teste."
                )
        finally:
            cap.stop()
            time.sleep(0.3)
            assert not cap.is_running

    # ------------------------------------------------------------------
    # E2E-08: Start/stop repetido — sem órfãos
    # ------------------------------------------------------------------

    def test_e2e_08_repeated_start_stop(self):
        """E2E-08: 5 ciclos de start/stop — sem pw-record órfão."""
        from src.audio.backends.pipewire.capture import PipewireCapture
        from src.audio.backends.pipewire.devices import list_pipewire_devices
        from src.platform.types import AudioCaptureConfig

        devices = list_pipewire_devices()
        if not devices:
            pytest.skip("Sem dispositivos para o teste")

        dev = devices[0]
        queue: multiprocessing.Queue = multiprocessing.Queue()

        for cycle in range(5):
            cap = PipewireCapture(device_id=dev.id, sample_rate=16000, chunk_size=480)
            try:
                cap.start(
                    AudioCaptureConfig(device_id=dev.id, sample_rate=16000, chunk_frames=480),
                    output_queue=queue,
                )
                assert cap.is_running, f"Ciclo {cycle}: backend não iniciou"
                time.sleep(0.5)
                cap.stop()
                time.sleep(0.3)
                assert not cap.is_running, f"Ciclo {cycle}: backend não parou"
            except Exception:
                cap.stop()
                raise

        # Após 5 ciclos, não pode haver pw-record órfão
        time.sleep(0.5)
        leaked = count_pw_record_processes() - self._initial_pw_record
        assert leaked == 0, (
            f"{leaked} processo(s) pw-record órfão(s) detectado(s) após 5 ciclos"
        )

    # ------------------------------------------------------------------
    # E2E-13: Seleção manual de dispositivo
    # ------------------------------------------------------------------

    def test_e2e_13_device_selection(self):
        """E2E-13: Seleciona dispositivo diferente e confirma uso."""
        from src.audio.backends.pipewire.capture import PipewireCapture
        from src.audio.backends.pipewire.devices import list_pipewire_devices
        from src.platform.types import AudioCaptureConfig

        devices = list_pipewire_devices()
        if len(devices) < 2:
            pytest.skip("Apenas 1 dispositivo — precisa de 2+ para validar seleção")

        dev_a, dev_b = devices[0], devices[1]
        queue: multiprocessing.Queue = multiprocessing.Queue()

        # Captura com dispositivo A
        cap_a = PipewireCapture(device_id=dev_a.id, sample_rate=16000, chunk_size=480)
        try:
            cap_a.start(
                AudioCaptureConfig(device_id=dev_a.id, sample_rate=16000, chunk_frames=480),
                output_queue=queue,
            )
            assert cap_a.is_running
            cmd_a = cap_a._build_cmd()
            assert "--target" in cmd_a
            assert dev_a.id in cmd_a
            time.sleep(0.5)
        finally:
            cap_a.stop()

        # Captura com dispositivo B
        cap_b = PipewireCapture(device_id=dev_b.id, sample_rate=16000, chunk_size=480)
        try:
            cap_b.start(
                AudioCaptureConfig(device_id=dev_b.id, sample_rate=16000, chunk_frames=480),
                output_queue=queue,
            )
            assert cap_b.is_running
            cmd_b = cap_b._build_cmd()
            assert dev_b.id in cmd_b
            assert dev_a.id not in cmd_b
            time.sleep(0.5)
        finally:
            cap_b.stop()

    # ------------------------------------------------------------------
    # E2E-14: Ausência de PipeWire — falha controlada
    # ------------------------------------------------------------------

    def test_e2e_14_no_pipewire_graceful_failure(self, monkeypatch):
        """E2E-14: Sem PipeWire, a fachada retorna [] e mensagem clara."""
        # Simula ausência de PipeWire
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: False)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: False)
        monkeypatch.setattr(detection, "_check_portal", lambda: False)

        from src.audio.backends import build_audio_backend, AudioBackendError
        with pytest.raises(AudioBackendError) as exc_info:
            build_audio_backend("auto")
        msg = str(exc_info.value)
        # Mensagem deve ser orientativa e em português
        assert "PipeWire" in msg or "servidor de áudio" in msg

    # ------------------------------------------------------------------
    # E2E-15: Regressão Windows isolada
    # ------------------------------------------------------------------

    def test_e2e_15_wasapi_never_on_linux(self, monkeypatch):
        """E2E-15: Backend WASAPI nunca é selecionado em Linux."""
        monkeypatch.setattr("sys.platform", "linux")
        from src.platform import detection
        monkeypatch.setattr(detection, "_check_pipewire_running", lambda: True)
        monkeypatch.setattr(detection, "_check_pulseaudio", lambda: True)

        from src.audio.backends import build_audio_backend
        backend = build_audio_backend("auto")
        from src.audio.backends.pipewire.capture import PipewireCapture
        assert isinstance(backend, PipewireCapture), (
            f"Em Linux, backend 'auto' deveria ser PipewireCapture, "
            f"não {type(backend).__name__}"
        )

    # ------------------------------------------------------------------
    # Validação de fixture sintética (não exige hardware)
    # ------------------------------------------------------------------

    def test_synthetic_fixture_format(self, sine_wave_pcm16):
        """Valida formato da fixture sintética (sem hardware)."""
        data = sine_wave_pcm16
        # 1s @ 16kHz = 16000 samples = 32000 bytes (s16le)
        assert len(data) == 32000
        # Não é silêncio (onda senoidal 440Hz amplitude 0.5)
        assert not is_silence(data)
        # Hash determinístico para evidência
        h = fixture_sha256(data)
        assert len(h) == 64  # SHA-256 hex
