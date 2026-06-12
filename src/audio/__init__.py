"""Módulo de captura e transcrição de áudio (Sprint 0+).

Submódulos:
    capture.py   — Loopback WASAPI com PyAudio
    vad.py       — Silero VAD para detecção de fala
    buffer.py    — Buffer circular thread-safe
    transcribe.py — faster-whisper (processo separado)
    diarize.py   — diart + pyannote (diarização)
    manager.py   — Coordenador do pipeline
    models.py    — Download/gerenciamento de modelos
"""
