"""Captura de áudio via pw-record (Linux).

Implementa o Protocol ``AudioCaptureBackend``. Usa subprocesso controlado
de ``pw-record`` para máxima estabilidade.

Estratégia:
    - Descoberta: ``pactl list sources`` (via ``devices.py``).
    - Captura: ``pw-record --target <id> --format f32 --rate 16000
      --channels 1 --latency 100ms -`` (lê PCM do stdout).
    - Conversão: ``f32 -> s16le`` em Python (numpy) — formato esperado
      pelo pipeline.
    - Lifecycle: SIGTERM no subprocesso ao parar; leitura em thread
      daemon para não bloquear a UI.
"""
from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import sys
import threading
from typing import IO

from src.audio.backends.pipewire.devices import list_pipewire_devices
from src.platform.types import AudioCaptureConfig, AudioDevice

_logger = logging.getLogger(__name__)

# 4 bytes por sample f32; chunk de 480 samples = 1920 bytes
_F32_BYTES_PER_SAMPLE = 4
_S16_BYTES_PER_SAMPLE = 2


class PipewireCapture:
    """Captura de áudio no Linux via subprocesso pw-record.

    Compatível com o Protocol ``AudioCaptureBackend``.
    """

    def __init__(
        self,
        device_id: str | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 480,
    ) -> None:
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.channels = 1
        self.chunk_size = chunk_size
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._queue = None
        self._stop_event = threading.Event()

    # -- AudioCaptureBackend Protocol ---------------------------------------

    def list_devices(self) -> list[AudioDevice]:
        return list_pipewire_devices()

    def start(self, config: AudioCaptureConfig, output_queue) -> None:
        """Inicia captura via pw-record."""
        if self._is_running:
            return
        if not shutil.which("pw-record"):
            raise RuntimeError(
                "pw-record não encontrado. Instale 'pipewire-utils' "
                "no Fedora: sudo dnf install pipewire-utils"
            )
        self._is_running = True
        self._queue = output_queue
        self.sample_rate = config.sample_rate
        self.channels = config.channels
        self.chunk_size = config.chunk_frames
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Para a captura graciosamente."""
        self._is_running = False
        self._stop_event.set()
        self._terminate_proc()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    # -- Interno ------------------------------------------------------------

    def _build_cmd(self) -> list[str]:
        cmd = [
            "pw-record",
            "--format", "f32",
            "--rate", str(self.sample_rate),
            "--channels", str(self.channels),
            "--latency", "100ms",
        ]
        if self.device_id is not None:
            # pw-record aceita ID numérico de source ou nome
            cmd.extend(["--target", str(self.device_id)])
        cmd.append("-")  # stdout
        return cmd

    def _capture_loop(self) -> None:
        cmd = self._build_cmd()
        _logger.info("Iniciando pw-record: %s", " ".join(cmd))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.chunk_size * _F32_BYTES_PER_SAMPLE * 4,
            )
        except FileNotFoundError as e:
            _logger.error("pw-record não disponível: %s", e)
            self._is_running = False
            return
        except Exception as e:
            _logger.error("Falha ao iniciar pw-record: %s", e)
            self._is_running = False
            return

        assert self._proc.stdout is not None
        try:
            self._pump_stdout(self._proc.stdout)
        except Exception as e:
            _logger.error("Loop de captura PipeWire falhou: %s", e)
        finally:
            self._terminate_proc()

    def _pump_stdout(self, stream: IO[bytes]) -> None:
        """Lê PCM f32 do stdout, converte para s16le, publica no queue."""
        import numpy as np

        bytes_per_chunk = self.chunk_size * _F32_BYTES_PER_SAMPLE
        while self._is_running and not self._stop_event.is_set():
            raw = stream.read(bytes_per_chunk)
            if not raw:
                # EOF — pw-record encerrou (dispositivo sumiu? permissão?)
                _logger.warning(
                    "pw-record encerrou stdout. stderr=%s",
                    self._read_stderr_nonblock(),
                )
                break
            if len(raw) < bytes_per_chunk:
                # Último fragmento — descartar (não preenche chunk inteiro)
                break

            # f32 -> s16le
            try:
                arr = (
                    np.frombuffer(raw, dtype=np.float32)
                    * 32767.0
                ).astype(np.int16)
                pcm_s16 = arr.tobytes()
            except Exception as e:
                _logger.warning("Falha na conversão PCM: %s", e)
                continue

            if self._queue is not None:
                try:
                    self._queue.put(pcm_s16)
                except Exception:
                    pass

    def _read_stderr_nonblock(self) -> str:
        """Lê stderr do pw-record sem bloquear (best-effort)."""
        if not self._proc or not self._proc.stderr:
            return ""
        import select
        try:
            r, _, _ = select.select([self._proc.stderr], [], [], 0.1)
            if r:
                return self._proc.stderr.read(4096).decode(
                    "utf-8", errors="replace"
                )
        except Exception:
            pass
        return ""

    def _terminate_proc(self) -> None:
        """Termina o subprocesso pw-record graciosamente."""
        if not self._proc:
            return
        try:
            if self._proc.poll() is None:
                # SIGTERM primeiro; força SIGKILL após 1.5s
                if sys.platform.startswith("win"):  # pragma: no cover
                    self._proc.terminate()
                else:
                    self._proc.send_signal(signal.SIGTERM)
                try:
                    self._proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=1.0)
        except Exception as e:
            _logger.warning("Erro ao terminar pw-record: %s", e)
        finally:
            self._proc = None
