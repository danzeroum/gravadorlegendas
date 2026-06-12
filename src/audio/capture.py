"""Captura de áudio via WASAPI loopback (Windows).

Usa PyAudio para capturar o áudio do sistema (saída das
aplicações). Requer Windows 10+ (1803+) e PyAudio.
"""
import threading
import multiprocessing


class AudioCapture:
    """Captura de áudio do sistema via loopback WASAPI.

    Attributes:
        sample_rate: Taxa de amostragem (Hz).
        channels: Número de canais.
        device_index: Índice do dispositivo WASAPI.
        chunk_size: Tamanho do chunk em frames.
    """

    def __init__(self, device_index: int | None = None,
                 sample_rate: int = 16000, chunk_size: int = 480):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = 1
        self.chunk_size = chunk_size
        self._stream = None
        self._thread: threading.Thread | None = None
        self._is_running = False

    def list_devices(self) -> list[dict]:
        """Lista dispositivos WASAPI com suporte a loopback.

        Returns:
            Lista de dicts com 'index', 'name', 'channels', 'rate'.
        """
        devices = []
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev["hostApi"] == wasapi["index"]:
                    devices.append({
                        "index": i,
                        "name": dev["name"],
                        "channels": dev.get("maxInputChannels", 0),
                        "rate": int(dev.get("defaultSampleRate", 0)),
                        "is_loopback": "loopback" in dev["name"].lower(),
                    })
            pa.terminate()
        except ImportError:
            pass
        return devices

    def start(self, output_queue: multiprocessing.Queue):
        """Inicia captura em thread separada.

        Args:
            output_queue: Queue onde chunks de áudio são enviados.
        """
        if self._is_running:
            return
        self._is_running = True
        self._queue = output_queue
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para a captura."""
        self._is_running = False
        if self._stream:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _capture_loop(self):
        """Loop de captura WASAPI em background."""
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            dev_index = self.device_index
            if dev_index is None:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                for i in range(pa.get_device_count()):
                    dev = pa.get_device_info_by_index(i)
                    if (dev["hostApi"] == wasapi["index"]
                            and "loopback" in dev["name"].lower()
                            and dev.get("maxInputChannels", 0) > 0):
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
                    self._queue.put(data)
                except Exception:
                    break
        finally:
            try:
                self._stream.close()
            except Exception:
                pass
            pa.terminate()
