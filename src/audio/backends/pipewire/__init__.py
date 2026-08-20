"""Backend PipeWire (Linux).

Usa ``pw-record`` (parte de ``pipewire-utils``) para gravar de qualquer
nó PipeWire — microfone ou monitor de saída. Decisão técnica:

Por que pw-record subprocess em vez de bindings Python diretos?
    - ``pygobject`` + ``gi.repository.Gst`` é pesado, instável em venv,
      e quebra frequentemente com mudanças de versão do PipeWire.
    - ``pw-link`` / ``pw-cli`` são suficientes para descoberta, mas não
      para gravação contínua.
    - ``pw-record`` é oficial, estável, leve, e gera WAV PCM 16-bit
      little-endian diretamente — exatamente o formato que o pipeline
      consome.
    - Gestão de lifecycle via subprocess é robusta: SIGTERM limpa
      recursos do PipeWire automaticamente.

Descoberta de dispositivos usa ``pactl list`` (funciona tanto com
PulseAudio quanto com PipeWire-Pulse), porque é o método mais portável
e não exige bindings Python.
"""
from src.audio.backends.pipewire.capture import PipewireCapture
from src.audio.backends.pipewire.devices import list_pipewire_devices

__all__ = ["PipewireCapture", "list_pipewire_devices"]
