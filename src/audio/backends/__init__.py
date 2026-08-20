"""Backends de captura de áudio.

Cada backend implementa o Protocol ``AudioCaptureBackend`` definido em
``src.platform.types``.

Backends disponíveis:
    wasapi/  — WasapiLoopbackCapture (Windows + PyAudio)
    pipewire/— PipewireCapture (Linux, via pw-record subprocess)

Use ``build_audio_backend()`` para construir o backend correto para a
plataforma atual — não importe os backends concretos diretamente fora
deste pacote.
"""
from src.audio.backends.factory import build_audio_backend, AudioBackendError

__all__ = ["build_audio_backend", "AudioBackendError"]
