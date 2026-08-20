"""Helpers compartilhados para testes de integração real.

Fornece:
- ``require_pipewire()`` — skip se PipeWire não estiver rodando.
- ``require_pactl()`` — skip se pactl não estiver disponível.
- ``require_x11()`` — skip se XDG_SESSION_TYPE != x11.
- ``require_stt_model()`` — skip se modelo Whisper não estiver em cache.
- ``generate_sine_wave_pcm16()`` — fixture sintética de áudio.
- ``count_pw_record_processes()`` — conta processos pw-record ativos.
- ``kill_orphan_pw_record()`` — mata pw-record órfão (cleanup).
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from src.audio.transcribe import WHISPER_DOWNLOAD_ROOT, whisper_model_dir


# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _pipewire_running() -> bool:
    if not _have("pw-cli"):
        return False
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    socket_path = os.path.join(runtime_dir, "pipewire-0") if runtime_dir else ""
    return bool(socket_path and os.path.exists(socket_path))


def require_pipewire():
    """Skip se PipeWire não está rodando."""
    if not _pipewire_running():
        pytest.skip("PipeWire não está rodando — teste requer PipeWire ativo")


def require_pactl():
    """Skip se pactl não está disponível."""
    if not _have("pactl"):
        pytest.skip("pactl não disponível — instale pipewire-pulseaudio ou pulseaudio-utils")


def require_x11():
    """Skip se sessão não é X11."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
        pytest.skip("Sessão não é X11 — teste requer X11 ativo")


def require_wayland():
    """Skip se sessão não é Wayland."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        pytest.skip("Sessão não é Wayland — teste requer Wayland ativo")


def require_display():
    """Skip se não há sessão gráfica."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session not in ("x11", "wayland"):
        pytest.skip("Sem sessão gráfica — teste requer X11 ou Wayland")


def require_stt_model(model_size: str = "base"):
    """Skip se modelo Whisper não está em cache.

    O cache é o mesmo usado pelo app (`src.audio.transcribe`) e pelo
    script `scripts/setup_audio_models.py --whisper <size>`:
    ~/.cache/gravador/audio/whisper/models--Systran--faster-whisper-<size>/
    """
    if not whisper_model_dir(model_size).exists():
        pytest.skip(
            f"Modelo Whisper '{model_size}' não encontrado em "
            f"{whisper_model_dir(model_size)}. "
            f"Baixe com: python3 scripts/setup_audio_models.py --whisper {model_size}"
        )


def require_tesseract():
    """Skip se Tesseract não está disponível."""
    if not _have("tesseract"):
        pytest.skip("Tesseract não encontrado no PATH")


# ---------------------------------------------------------------------------
# Fixtures de áudio sintético
# ---------------------------------------------------------------------------

def generate_sine_wave_pcm16(
    duration_s: float = 1.0,
    frequency: float = 440.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> bytes:
    """Gera onda senoidal PCM s16le para usar como fixture sintética.

    Não usa rede nem hardware. O áudio é determinístico (mesmo seed).
    Útil para validar formato de chunks sem depender de microfone real.
    """
    n_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        value = amplitude * math.sin(2 * math.pi * frequency * t)
        # Converte float [-1.0, 1.0] -> int16 [-32768, 32767]
        int_val = int(value * 32767)
        samples.append(struct.pack("<h", int_val))
    return b"".join(samples)


def fixture_sha256(data: bytes) -> str:
    """Calcula SHA-256 de uma fixture (para registro em evidências)."""
    return hashlib.sha256(data).hexdigest()


def is_silence(pcm16: bytes, threshold: int = 50) -> bool:
    """Detecta se um chunk PCM s16le é silêncio (todas as amostras < threshold)."""
    if len(pcm16) < 2:
        return True
    n_samples = len(pcm16) // 2
    for i in range(n_samples):
        sample = struct.unpack("<h", pcm16[i * 2 : i * 2 + 2])[0]
        if abs(sample) > threshold:
            return False
    return True


# ---------------------------------------------------------------------------
# Gestão de processos pw-record
# ---------------------------------------------------------------------------

def count_pw_record_processes() -> int:
    """Conta processos pw-record ativos no sistema."""
    try:
        result = subprocess.run(
            ["pgrep", "-c", "pw-record"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0


def kill_orphan_pw_record(timeout_s: float = 2.0) -> int:
    """Mata processos pw-record órfãos. Retorna número de processos mortos.

    Usado em cleanup de testes para garantir que não haja vazamento.
    """
    killed = 0
    try:
        result = subprocess.run(
            ["pgrep", "pw-record"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            pids = [int(p) for p in result.stdout.split() if p.strip()]
            for pid in pids:
                try:
                    os.kill(pid, 15)  # SIGTERM
                    killed += 1
                except (ProcessLookupError, PermissionError):
                    pass
            # Aguarda terminar
            import time
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                if count_pw_record_processes() == 0:
                    break
                time.sleep(0.1)
            # SIGKILL nos restantes
            for pid in pids:
                try:
                    os.kill(pid, 9)  # SIGKILL
                except (ProcessLookupError, PermissionError):
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return killed


# ---------------------------------------------------------------------------
# pytest fixtures reutilizáveis
# ---------------------------------------------------------------------------

@pytest.fixture
def sine_wave_pcm16():
    """Fixture: 1 segundo de onda senoidal 440Hz PCM s16le 16kHz mono."""
    return generate_sine_wave_pcm16(duration_s=1.0, frequency=440.0)


@pytest.fixture
def sine_wave_pcm16_short():
    """Fixture: 30ms de onda senoidal (480 samples @ 16kHz)."""
    return generate_sine_wave_pcm16(duration_s=0.03, frequency=440.0)
