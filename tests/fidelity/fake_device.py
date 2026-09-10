"""Subprocesso pw-record sintético para testes offline de captura.

Fornece um ``Popen`` fake cujo stdout entrega um stream f32 determinístico,
permitindo exercitar o loop de captura **REAL** do ``PipewireCapture``
(thread, conversão f32→s16le com sanitização de NaN/Inf, publicação em
fila, terminação de subprocesso, drenagem) **sem hardware PipeWire**.

Classificação honesta (ver docs/qualidade-audio/README.md):
    integração com código real, offline, sem hardware — o código de
    produção roda de ponta a ponta; apenas o *device* é sintético.

Testes que exigem PipeWire de verdade usam o marker ``requires_pipewire``
e estão em tests/integration/ (inalterados).
"""
from __future__ import annotations

import contextlib
import io
import queue as queue_mod
import signal as signal_mod
import threading
import time
from unittest.mock import patch

import numpy as np

from src.audio.backends.pipewire import capture as pw_capture_mod
from src.platform.types import AudioCaptureConfig

PW_CAPTURE_MODULE = "src.audio.backends.pipewire.capture"


class FakePwRecordProcess:
    """Objeto Popen-like mínimo exigido por ``PipewireCapture``.

    Implementa exatamente a superfície usada pelo código de produção:
    ``stdout``, ``stderr``, ``poll()``, ``send_signal()``, ``terminate()``,
    ``kill()`` e ``wait()``.
    """

    def __init__(self, stdout_data: bytes, stderr_data: bytes = b"") -> None:
        self.stdout = io.BytesIO(stdout_data)
        self.stderr = io.BytesIO(stderr_data)
        self.returncode: int | None = None
        self.signals: list[int] = []
        self.lock = threading.Lock()

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, sig: int) -> None:
        with self.lock:
            self.signals.append(int(sig))
            if self.returncode is None:
                self.returncode = -int(sig)

    def terminate(self) -> None:
        self.send_signal(signal_mod.SIGTERM)

    def kill(self) -> None:
        with self.lock:
            self.signals.append(signal_mod.SIGKILL)
            self.returncode = -9

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode


class TimingQueue(queue_mod.Queue):
    """Queue que registra timestamp monotônico de cada ``put``.

    Usado para medir jitter de entrega de chunks (FID-10) sem depender
    de wall-clock absoluto como gate rígido.
    """

    def __init__(self) -> None:
        super().__init__()
        self.put_timestamps: list[float] = []

    def put(self, item, block=True, timeout=None):  # noqa: A003
        self.put_timestamps.append(time.monotonic())
        super().put(item, block, timeout)


@contextlib.contextmanager
def synthetic_pw_record(f32_bytes: bytes, stderr: bytes = b""):
    """Patching de ``which``/``Popen`` para captura com stream sintético.

    Yields um dict com ``proc`` (FakePwRecordProcess criado) e ``cmd``
    (linha de comando construída pelo código real).
    """
    holder: dict = {}

    def fake_popen(cmd, **kwargs):
        proc = FakePwRecordProcess(f32_bytes, stderr)
        holder["proc"] = proc
        holder["cmd"] = list(cmd)
        return proc

    with patch(
        f"{PW_CAPTURE_MODULE}.shutil.which",
        return_value="/usr/bin/pw-record",
    ):
        with patch(
            f"{PW_CAPTURE_MODULE}.subprocess.Popen",
            side_effect=fake_popen,
        ):
            yield holder


def f32_bytes(signal: np.ndarray) -> bytes:
    """Serializa sinal float para bytes f32 little-endian (formato pw-record)."""
    return np.asarray(signal, dtype=np.float32).tobytes()


def drain_all(q) -> list:
    """Esvazia a fila de forma determinística (sem sleeps)."""
    chunks = []
    while True:
        try:
            chunks.append(q.get_nowait())
        except queue_mod.Empty:
            return chunks


def run_pipewire_capture(
    signal_f32: np.ndarray,
    sample_rate: int = 16000,
    chunk_frames: int = 480,
    device_id: str = "42",
    queue_impl=None,
):
    """Roda o ``PipewireCapture`` real com device sintético até o EOF.

    Sequência determinística: start → join da thread interna (o pump
    termina sozinho no EOF) → drenagem completa da fila → stop.
    Sem sleeps arbitrários: a sincronização é o join da thread.

    Returns:
        Tuple ``(capture, chunks, holder)`` — instância real, chunks
        publicados e holder do processo fake (cmd/signals).
    """
    q = queue_impl() if queue_impl else queue_mod.Queue()
    cap = pw_capture_mod.PipewireCapture(
        device_id=device_id,
        sample_rate=sample_rate,
        chunk_size=chunk_frames,
    )
    config = AudioCaptureConfig(
        device_id=device_id,
        sample_rate=sample_rate,
        channels=1,
        chunk_frames=chunk_frames,
    )
    with synthetic_pw_record(f32_bytes(signal_f32)) as holder:
        cap.start(config, q)
        thread = getattr(cap, "_thread", None)
        if thread is not None:
            thread.join(timeout=15.0)
            assert not thread.is_alive(), (
                "thread de captura não terminou no prazo — pump travado"
            )
        chunks = drain_all(q)
        cap.stop()
    return cap, chunks, holder
