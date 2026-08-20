"""Tipos e interfaces (Protocol) usados pela camada de plataforma.

Centraliza as dataclasses e Protocol que os backends concretos precisam
implementar. Mantidos aqui — e não em ``src/audio/`` ou ``src/capture/`` —
para que a camada de plataforma seja a única fonte de verdade sobre o
contrato que backends de áudio/tela/legendas devem satisfazer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AudioDevice:
    """Descrição agnóstica de plataforma de um dispositivo de áudio.

    Attributes:
        id: Identificador único estável no backend (índice PyAudio,
            caminho PulseAudio, node id PipeWire, etc.).
        name: Nome amigável exibido na UI.
        kind: "input" (microfone), "output" (saída/loopback), "monitor"
            (fonte de monitor PipeWire), "unknown".
        channels: Número de canais suportados.
        sample_rate: Taxa de amostragem nativa (Hz).
        is_default: Se é o dispositivo padrão do backend.
        backend: Nome do backend que o expôs ("wasapi", "pipewire"...).
    """

    id: str
    name: str
    kind: str = "unknown"
    channels: int = 1
    sample_rate: int = 16000
    is_default: bool = False
    backend: str = ""


@dataclass
class AudioCaptureConfig:
    """Configuração para iniciar um backend de captura de áudio.

    Attributes:
        device_id: Identificador do dispositivo (None = padrão do backend).
        sample_rate: Taxa alvo (Hz). Backend deve resamplear se necessário.
        channels: Canais alvo (1 = mono). Backend deve mixar down se necessário.
        chunk_frames: Tamanho do chunk em frames.
        format: Sempre "pcm_s16le" — formato esperado pelo pipeline
            (VAD, diarização, transcrição).
    """

    device_id: str | None = None
    sample_rate: int = 16000
    channels: int = 1
    chunk_frames: int = 480
    format: str = "pcm_s16le"


@dataclass
class AudioChunk:
    """Chunk de áudio PCM 16-bit little-endian, mono, 16kHz.

    Esse é o formato canônico consumido por VAD, buffer, diarização e
    transcrição. Backends devem converter qualquer formato nativo para
    este formato antes de publicar.
    """

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    timestamp: float = 0.0


@runtime_checkable
class AudioCaptureBackend(Protocol):
    """Contrato para backends de captura de áudio.

    Implementações concretas:
        - ``src.audio.backends.wasapi.WasapiLoopbackCapture`` (Windows)
        - ``src.audio.backends.pipewire.PipewireCapture`` (Linux)
    """

    def list_devices(self) -> list[AudioDevice]: ...

    def start(self, config: AudioCaptureConfig, output_queue) -> None: ...

    def stop(self) -> None: ...

    @property
    def is_running(self) -> bool: ...


@runtime_checkable
class CaptionSource(Protocol):
    """Contrato para fontes de legendas.

    Implementações concretas:
        - ``src.caption.windows_live.WindowsLiveCaptionsSource`` (Windows)
        - ``src.caption.local_stt.LocalSTTSource`` (Win + Linux)
        - ``src.caption.screen_ocr.ScreenOCRSource`` (Win + Linux X11)
    """

    def start(self) -> None: ...

    def stop(self) -> None: ...

    @property
    def is_running(self) -> bool: ...
