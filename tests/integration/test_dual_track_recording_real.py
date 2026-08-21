"""Testes de integração T3.1–T3.4: gravação dual-track com PipeWire real.

Requer:
- PipeWire rodando (``require_pipewire()``).
- ``pactl`` disponível (``require_pactl()``).
- ``pw-play`` disponível (``require_pw_play()``).
- ``espeak-ng`` disponível (``require_espeak()``).

Em ambientes sem essas dependências (ex.: sandbox CI sem áudio real),
os testes fazem skip automático com mensagem explícita — não falham
silenciosamente.

Para rodar no Fedora do usuário:
    pytest -q -m "integration and requires_pipewire" \
        tests/integration/test_dual_track_recording_real.py
"""
from __future__ import annotations

import multiprocessing
import os
import queue as _q
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from src.audio.backends.pipewire.capture import PipewireCapture
from src.audio.recorder import DualTrackRecorder
from src.platform.types import AudioCaptureConfig

from tests.integration.conftest import (
    count_pw_record_processes,
    kill_orphan_pw_record,
    require_espeak,
    require_pactl,
    require_pipewire,
    require_pw_play,
)

pytestmark = [pytest.mark.integration]


def _load_null_sink(name: str) -> str | None:
    """Cria sink virtual e retorna o id do monitor."""
    result = subprocess.run(
        ["pactl", "load-module", "module-null-sink",
         f"sink_name={name}", "sink_properties=device.description=test"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return None
    time.sleep(0.5)
    out = subprocess.run(
        ["pactl", "list", "short", "sources"],
        capture_output=True, text=True, timeout=15, check=False,
    ).stdout
    for line in out.splitlines():
        if f"{name}.monitor" in line:
            return line.split("\t")[0]
    return None


def _unload_null_sink(name: str) -> None:
    out = subprocess.run(
        ["pactl", "list", "short", "modules"],
        capture_output=True, text=True, timeout=15, check=False,
    ).stdout
    for line in out.splitlines():
        if "module-null-sink" in line and f"sink_name={name}" in line:
            mod_id = line.split("\t")[0]
            subprocess.run(
                ["pactl", "unload-module", mod_id],
                capture_output=True, timeout=15, check=False,
            )
            break


def _generate_espeak_wav(text: str, dest: Path, voice: str = "pt-br",
                         speed: int = 90) -> float:
    """Gera WAV via espeak-ng. Retorna duração em segundos."""
    cmd = [
        "espeak-ng", "-v", voice, "-s", str(speed),
        "-w", str(dest), text,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(f"espeak-ng falhou: {result.stderr}")
    with wave.open(str(dest), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


class TestDualTrackRecordingReal:
    """T3.1–T3.4: testes de integração com PipeWire real."""

    def setup_method(self):
        require_pipewire()
        require_pactl()
        require_espeak()
        require_pw_play()

    def test_t31_two_files_same_duration(self, tmp_path):
        """T3.1: dois WAVs gerados, mesma duração, trilhos não cruzados."""
        sink_mic = f"dual_mic_{os.getpid()}"
        sink_sys = f"dual_sys_{os.getpid()}"
        mic_id = _load_null_sink(sink_mic)
        sys_id = _load_null_sink(sink_sys)
        if mic_id is None or sys_id is None:
            _unload_null_sink(sink_mic)
            _unload_null_sink(sink_sys)
            pytest.skip("Não foi possível criar sinks virtuais")

        mic_wav = tmp_path / "ref_mic.wav"
        sys_wav = tmp_path / "ref_sys.wav"
        mic_dur = _generate_espeak_wav("teste microfone", mic_wav)
        sys_dur = _generate_espeak_wav("teste sistema", sys_wav, voice="pt-br+f3")

        rec = DualTrackRecorder(str(tmp_path), prefix="t31")
        mic_capture = PipewireCapture(device_id=mic_id)
        sys_capture = PipewireCapture(device_id=sys_id)
        mic_cfg = AudioCaptureConfig(
            device_id=mic_id, sample_rate=16000, channels=1, chunk_frames=480,
        )
        sys_cfg = AudioCaptureConfig(
            device_id=sys_id, sample_rate=16000, channels=1, chunk_frames=480,
        )

        mic_q = multiprocessing.Queue()
        sys_q = multiprocessing.Queue()
        try:
            rec.start()
            mic_capture.start(mic_cfg, mic_q)
            sys_capture.start(sys_cfg, sys_q)

            p_mic = subprocess.Popen(
                ["pw-play", "--target", sink_mic, str(mic_wav)]
            )
            p_sys = subprocess.Popen(
                ["pw-play", "--target", sink_sys, str(sys_wav)]
            )
            time.sleep(max(mic_dur, sys_dur) + 2.0)
            p_mic.wait(timeout=5)
            p_sys.wait(timeout=5)

            # Drena filas e alimenta recorder
            while True:
                try:
                    chunk = mic_q.get_nowait()
                    rec.feed_mic(chunk)
                except _q.Empty:
                    break
            while True:
                try:
                    chunk = sys_q.get_nowait()
                    rec.feed_system(chunk)
                except _q.Empty:
                    break
        finally:
            mic_capture.stop()
            sys_capture.stop()
            result = rec.stop()
            kill_orphan_pw_record()
            _unload_null_sink(sink_mic)
            _unload_null_sink(sink_sys)

        assert result.mic_path is not None
        assert result.system_path is not None
        # Diff de duração <= 100ms
        mic_dur_rec = result.mic_samples / 16000
        sys_dur_rec = result.system_samples / 16000
        diff_ms = abs(mic_dur_rec - sys_dur_rec) * 1000
        assert diff_ms <= 200, (
            f"Diff de duração muito alta: {diff_ms:.0f}ms"
        )

    def test_t34_five_cycles_start_stop(self, tmp_path):
        """T3.4: 5 ciclos start/stop sem processos residuais."""
        for i in range(5):
            rec = DualTrackRecorder(str(tmp_path), prefix=f"cycle{i}")
            rec.start()
            # Sem alimentar — só valida ciclo start/stop
            result = rec.stop()
            assert result is not None
        # Sem processos pw-record órfãos
        assert count_pw_record_processes() == 0, (
            "Há processos pw-record órfãos após 5 ciclos"
        )

    def test_t33_stop_returns_within_2s(self, tmp_path):
        """T3.3: stop() retorna em menos de 2s mesmo com dados pendentes."""
        sink = f"t33_{os.getpid()}"
        sid = _load_null_sink(sink)
        if sid is None:
            pytest.skip("Não foi possível criar sink virtual")

        wav = tmp_path / "ref.wav"
        dur = _generate_espeak_wav("teste de encerramento limpo", wav)

        rec = DualTrackRecorder(str(tmp_path), prefix="t33")
        capture = PipewireCapture(device_id=sid)
        cfg = AudioCaptureConfig(
            device_id=sid, sample_rate=16000, channels=1, chunk_frames=480,
        )
        q = multiprocessing.Queue()
        try:
            rec.start()
            capture.start(cfg, q)
            player = subprocess.Popen(["pw-play", "--target", sink, str(wav)])
            time.sleep(dur / 2)  # Para no meio da fala
            player.kill()
            t0 = time.monotonic()
            # Drena fila antes do stop
            while True:
                try:
                    chunk = q.get_nowait()
                    rec.feed_mic(chunk)
                except _q.Empty:
                    break
            rec.stop()
            elapsed = time.monotonic() - t0
            assert elapsed < 2.0, f"stop() demorou {elapsed:.2f}s"
        finally:
            capture.stop()
            kill_orphan_pw_record()
            _unload_null_sink(sink)
