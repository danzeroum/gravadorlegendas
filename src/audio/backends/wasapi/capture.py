"""Captura WASAPI loopback (Windows) — refatorado como backend.

Implementa o Protocol ``AudioCaptureBackend``. Mantém o comportamento
original do ``AudioCapture`` legado para não regredir o fluxo Windows.

Requer:
    - Windows 10+ (1803+)
    - PyAudio instalado (``pip install PyAudio``)
"""
from __future__ import annotations

import logging
import threading

from src.platform.types import AudioCaptureConfig, AudioDevice

_logger = logging.getLogger(__name__)


class WasapiLoopbackCapture:
    """Captura de áudio do sistema via loopback WASAPI.

    Compatível com o Protocol ``AudioCaptureBackend``.
    """

    def __init__(
        self,
        device_index: int | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 480,
    ) -> None:
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = 1
        self.chunk_size = chunk_size
        self._stream = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._queue = None

    # -- AudioCaptureBackend Protocol ---------------------------------------

    def list_devices(self) -> list[AudioDevice]:
        """Lista dispositivos WASAPI com suporte a loopback."""
        devices: list[AudioDevice] = []
        try:
            import pyaudio  # type: ignore[import-not-found]

            pa = pyaudio.PyAudio()
            try:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            except Exception as e:
                _logger.warning("WASAPI não disponível: %s", e)
                pa.terminate()
                return devices

            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev["hostApi"] != wasapi["index"]:
                    continue
                is_lb = "loopback" in dev["name"].lower()
                devices.append(
                    AudioDevice(
                        id=str(i),
                        name=dev["name"],
                        kind="output" if is_lb else "input",
                        channels=int(dev.get("maxInputChannels", 0) or 0),
                        sample_rate=int(dev.get("defaultSampleRate", 0) or 0),
                        is_default=False,
                        backend="wasapi",
                    )
                )
            pa.terminate()
        except ImportError:
            _logger.debug("PyAudio não instalado; list_devices retorna [].")
        return devices

    def start(self, config: AudioCaptureConfig, output_queue) -> None:
        """Inicia captura em thread separada."""
        if self._is_running:
            return
        self._is_running = True
        self._queue = output_queue
        self.sample_rate = config.sample_rate
        self.channels = config.channels
        self.chunk_size = config.chunk_frames
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Para a captura."""
        self._is_running = False
        if self._stream:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    # -- Loop interno (mantém lógica original) -----------------------------

    def _capture_loop(self) -> None:
        import pyaudio  # type: ignore[import-not-found]

        pa = pyaudio.PyAudio()
        try:
            dev_index = self.device_index
            if dev_index is None:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                for i in range(pa.get_device_count()):
                    dev = pa.get_device_info_by_index(i)
                    if (
                        dev["hostApi"] == wasapi["index"]
                        and "loopback" in dev["name"].lower()
                        and dev.get("maxInputChannels", 0) > 0
                    ):
                        dev_index = i
                        break
            if dev_index is None:
                dev_index = pa.get_default_input_device_info()["index"]

            self._stream = pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=dev_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=None,
            )
            self._stream.start_stream()

            while self._is_running:
                try:
                    data = self._stream.read(
                        self.chunk_size, exception_on_overflow=False
                    )
                    if self._queue is not None:
                        self._queue.put(data)
                except Exception:
                    break
        finally:
            try:
                if self._stream:
                    self._stream.close()
            except Exception:
                pass
            pa.terminate()
