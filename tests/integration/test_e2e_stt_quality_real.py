"""E2E-07 (real): qualidade STT com áudio de sistema controlado.

Reproduz a frase de referência em português ("teste de transcrição local
no Fedora") no sink PipeWire usando espeak-ng (voz pt-br lenta), captura o
monitor de áudio com o pipeline real do app (PipewireCapture ->
TranscriberProcess com as configurações de qualidade validadas) e exige
que a transcrição normalizada contenha pelo menos 2 termos-chave.

Só PASS se a fidelidade STT for reconhecível semanticamente. Skip se o
ambiente não tiver PipeWire, modelo Whisper em cache, espeak-ng ou pw-play.

Rodar:
    pytest -q -m "integration and requires_stt_model" \
        tests/integration/test_e2e_stt_quality_real.py
"""
from __future__ import annotations

import os
import queue
import subprocess
import time
import unicodedata
import wave
from pathlib import Path

import pytest

from src.audio.backends.pipewire.capture import PipewireCapture
from src.audio.backends.pipewire.devices import list_pipewire_devices
from src.audio.transcribe import TranscriberProcess
from src.platform.types import AudioCaptureConfig

from tests.integration.conftest import (
    count_pw_record_processes,
    kill_orphan_pw_record,
    require_espeak,
    require_pactl,
    require_pipewire,
    require_pw_play,
    require_stt_model,
)

REFERENCE_PHRASE = "teste de transcrição local no Fedora"
REFERENCE_TARGET_TERMS = ["teste", "transcrição", "local", "fedora"]
MIN_TARGET_TERMS = 2
ESPEAK_LANGUAGE = "pt-br"
ESPEAK_SPEED = 90  # lenta: voz sintética nessa velocidade transcreve fielmente
ESPEAK_GAP = 8  # pausa entre palavras (ms)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_stt_model,
]


def _normalize(text: str) -> str:
    """Minúsculas, sem acentos e apenas alfanuméricos (palavras)."""
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.lower().split())


def _count_target_terms(text: str) -> int:
    """Conta termos únicos da frase de referência presentes na transcrição."""
    norm = _normalize(text.lower())
    words = set(norm.split())
    return sum(1 for term in REFERENCE_TARGET_TERMS if _normalize(term) in words)


def _generate_reference_wav(dest: Path) -> float:
    """Gera a frase de referência com espeak-ng. Retorna a duração (s)."""
    cmd = [
        "espeak-ng",
        "-v", ESPEAK_LANGUAGE,
        "-s", str(ESPEAK_SPEED),
        "-g", str(ESPEAK_GAP),
        "-w", str(dest),
        REFERENCE_PHRASE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(f"espeak-ng falhou: {result.stderr or result.stdout}")
    with wave.open(str(dest), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
    if frames <= 0 or rate <= 0:
        raise RuntimeError("Fixture WAV inválida")
    return frames / rate


def _find_monitor_device():
    """Retorna o primeiro source de monitor PipeWire (None se não houver)."""
    for dev in list_pipewire_devices():
        if dev.kind == "monitor":
            return dev
    return None


def _load_null_sink(name: str) -> str | None:
    """Cria um sink virtual (module-null-sink) para captura isolada.

    O sink virtual tem um monitor próprio que só captura o que for
    reproduzido nele. Isso isola a frase de referência de qualquer áudio
    ambiente do sistema (podcast, vídeo, chamada), garantindo um teste
    determinístico. Retorna o id do monitor (None se falhou).
    """
    result = subprocess.run(
        ["pactl", "load-module", "module-null-sink",
         f"sink_name={name}", "sink_properties=device.description=STT isolado"],
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
    """Remove o sink virtual criado por _load_null_sink."""
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


def _collect_transcripts(in_q, out_q, settle_s: float = 10.0, deadline_s: float = 300.0):
    """Coleta transcrições até o pipeline estabilizar ou estourar prazo."""
    texts: list[str] = []
    last_activity = time.monotonic()
    deadline = last_activity + deadline_s
    while time.monotonic() < deadline:
        drained = 0
        while True:
            try:
                item = out_q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, dict) and item.get("text"):
                texts.append(item["text"])
            drained += 1
        if drained:
            last_activity = time.monotonic()
        idle = time.monotonic() - last_activity
        if in_q.empty() and idle >= settle_s:
            break
        time.sleep(0.5)
    return texts


class TestSTTQualityReal:
    """E2E-07: fidelidade de transcrição de áudio de sistema controlado."""

    def setup_method(self):
        require_pipewire()
        require_pactl()
        require_stt_model("base")

    def test_e2e_07_stt_quality_system_audio(self, tmp_path):
        require_espeak()
        require_pw_play()

        sink_name = f"stt_test_{os.getpid()}"
        monitor_id = _load_null_sink(sink_name)
        if monitor_id is None:
            pytest.skip("Não foi possível criar sink virtual isolado (module-null-sink)")

        # Gera a fixture de referência (frase PT conhecida) e mede duração.
        fixture = tmp_path / "referencia.wav"
        phrase_dur = _generate_reference_wav(fixture)

        import multiprocessing
        in_q = multiprocessing.Queue()
        out_q = multiprocessing.Queue()

        transcriber = TranscriberProcess(
            in_q,
            out_q,
            model_size="base",
            chunk_duration=7.0,
            language="pt",
            task="transcribe",
            beam_size=1,
            temperature=0.0,
            vad_filter=True,
        )
        transcriber.start()

        capture = PipewireCapture(device_id=monitor_id)
        config = AudioCaptureConfig(
            device_id=monitor_id,
            sample_rate=16000,
            channels=1,
            chunk_frames=480,
        )

        results: list[str] = []
        try:
            capture.start(config, in_q)
            time.sleep(1.0)  # deixa o pw-record estabilizar

            player = subprocess.Popen(
                ["pw-play", "--target", sink_name, str(fixture)]
            )
            try:
                player.wait(timeout=30)
            except subprocess.TimeoutExpired:
                player.kill()
                player.wait()

            capture_window = phrase_dur + 3.0
            time.sleep(capture_window)

            capture.stop()
            results = _collect_transcripts(in_q, out_q)
        finally:
            capture.stop()
            transcriber.stop()
            transcriber.join(timeout=20)
            # Drena o que ainda estiver na fila de saída
            try:
                while True:
                    item = out_q.get_nowait()
                    if isinstance(item, dict) and item.get("text"):
                        results.append(item["text"])
            except queue.Empty:
                pass
            kill_orphan_pw_record()
            _unload_null_sink(sink_name)

        combined = " ".join(results)
        n_terms = _count_target_terms(combined)

        # Evidência para o relatório de validação
        print(f"\n[STT] frase referência: {REFERENCE_PHRASE!r}")
        print(f"[STT] transcrição: {combined!r}")
        print(f"[STT] termos únicos encontrados: {n_terms}/{MIN_TARGET_TERMS}")

        assert combined.strip(), "Nenhuma transcrição produzida — pipeline STT falhou"
        assert n_terms >= MIN_TARGET_TERMS, (
            f"Fidelidade STT insuficiente: {n_terms} de {len(REFERENCE_TARGET_TERMS)} "
            f"termos em {combined!r}"
        )
        assert count_pw_record_processes() == 0, (
            "Há processos pw-record órfãos após o encerramento — vazamento de processo"
        )


class TestSTTQualityHelpers:
    """Testes unitários dos helpers do teste de qualidade STT."""

    def test_normalize_removes_accents_and_case(self):
        assert _normalize("Transcrição, Local! Fedora?") == "transcricao local fedora"

    def test_count_target_terms(self):
        assert _count_target_terms("teste de transcricao local no fedora") == 4
        assert _count_target_terms("teste local") == 2
        assert _count_target_terms("tasti fedlora") == 0
