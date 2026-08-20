"""Módulo de captura e transcrição de áudio.

Submódulos:
    backends/    — Backends concretos (WasapiLoopbackCapture, PipewireCapture)
    capture.py   — Fachada retrocompatível delegando ao backend selecionado
    vad.py       — Silero VAD para detecção de fala
    buffer.py    — Buffer circular thread-safe
    transcribe.py — faster-whisper (processo separado)
    diarize.py   — diart + pyannote (diarização)
    manager.py   — Coordenador do pipeline
    metrics.py   — Telemetria (latência, sobreposição)
    models.py    — Download/gerenciamento de modelos
"""
