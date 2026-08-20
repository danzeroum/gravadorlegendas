"""Fábrica de backends de captura de áudio.

Centraliza a construção com base na seleção automática de plataforma.
"""
from __future__ import annotations

from src.platform.detection import detect_capabilities
from src.platform.selector import select_audio_backend, BackendSelectionError
from src.platform.types import AudioCaptureBackend


class AudioBackendError(RuntimeError):
    """Erro de construção de backend de áudio."""


def build_audio_backend(
    requested: str = "auto",
    device_id: str | int | None = None,
    sample_rate: int = 16000,
    chunk_size: int = 480,
) -> AudioCaptureBackend:
    """Constrói o backend de áudio apropriado.

    Args:
        requested: "auto" | "wasapi" | "pipewire".
        device_id: Identificador do dispositivo (None = padrão do backend).
            Para WASAPI, é índice inteiro; para PipeWire, é ID numérico
            ou nome do source.
        sample_rate: Taxa alvo (Hz).
        chunk_size: Tamanho do chunk em frames.

    Returns:
        Instância concreta implementando ``AudioCaptureBackend``.

    Raises:
        AudioBackendError: Se o backend não puder ser construído.
    """
    caps = detect_capabilities()
    try:
        chosen = select_audio_backend(requested, caps)
    except BackendSelectionError as e:
        raise AudioBackendError(str(e)) from e

    if chosen == "wasapi":
        from src.audio.backends.wasapi.capture import WasapiLoopbackCapture
        # WASAPI usa device_index (int) historicamente
        dev_idx = int(device_id) if device_id is not None else None
        return WasapiLoopbackCapture(
            device_index=dev_idx,
            sample_rate=sample_rate,
            chunk_size=chunk_size,
        )

    if chosen == "pipewire":
        from src.audio.backends.pipewire.capture import PipewireCapture
        # PipeWire usa device_id (str)
        dev_id = str(device_id) if device_id is not None else None
        return PipewireCapture(
            device_id=dev_id,
            sample_rate=sample_rate,
            chunk_size=chunk_size,
        )

    raise AudioBackendError(f"Backend de áudio não suportado: {chosen!r}")
