"""Backend WASAPI loopback (Windows).

Wrapper sobre o PyAudio original do projeto, refatorado para satisfazer
o Protocol ``AudioCaptureBackend``. Mantém a lógica intacta para
compatibilidade com o fluxo Windows já testado.
"""
from src.audio.backends.wasapi.capture import WasapiLoopbackCapture

__all__ = ["WasapiLoopbackCapture"]
