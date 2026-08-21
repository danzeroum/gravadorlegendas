"""Testes de integração T5.1–T5.5: RNNoise com PipeWire + Whisper real.

Requer:
- PipeWire rodando (``require_pipewire()``).
- ``pactl`` disponível (``require_pactl()``).
- ``pw-play`` disponível (``require_pw_play()``).
- ``espeak-ng`` disponível (``require_espeak()``).
- ``ffmpeg`` ou ``sox`` (para gerar ruído sintético).
- Modelo Whisper ``base`` em cache.
- Binding RNNoise (``pyrnnoise`` ou ``rnnoise_wrapper``) — se ausente,
  o filtro cai para o fallback espectral (logado).

Em ambientes sem essas dependências, os testes fazem skip automático.
"""
from __future__ import annotations

import multiprocessing
import os
import queue as _q
import subprocess
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np
import pytest

from src.audio.transcribe import TranscriberProcess
from src.filter.noise_suppression import RNNoiseFilter
from src.platform.types import AudioCaptureConfig
from src.audio.backends.pipewire.capture import PipewireCapture

from tests.integration.conftest import (
    count_pw_record_processes,
    kill_orphan_pw_record,
    require_espeak,
    require_pactl,
    require_pipewire,
    require_pw_play,
    require_stt_model,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_stt_model,
]

REFERENCE_PHRASE = "teste de transcrição local no Fedora"
REFERENCE_TERMS = ["teste", "transcricao", "local", "fedora"]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _count_terms(text: str) -> int:
    words = set(_normalize(text).split())
    return sum(1 for t in REFERENCE_TERMS if _normalize(t) in words)


def _load_null_sink(name: str) -> str | None:
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


def _generate_espeak_wav(text: str, dest: Path) -> float:
    cmd = ["espeak-ng", "-v", "pt-br", "-s", "90", "-w", str(dest), text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"espeak-ng: {r.stderr}")
    with wave.open(str(dest), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _generate_noisy_wav(clean_wav: Path, out_wav: Path,
                        noise_freq: float = 800.0) -> None:
    """Adiciona ruído tonal (zumbido) ao WAV limpo via ffmpeg."""
    # Usa ffmpeg para sobrepor tom senoidal
    cmd = [
        "ffmpeg", "-y",
        "-i", str(clean_wav),
        "-f", "lavfi", "-i", f"sine=frequency={noise_freq}:sample_rate=16000",
        "-filter_complex", "[0:a]volume=1.0[a0];[1:a]volume=0.3[a1];"
                          "[a0][a1]amix=inputs=2:duration=first[a]",
        "-map", "[a]",
        "-ar", "16000", "-ac", "1",
        str(out_wav),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.skip(f"ffmpeg falhou ao gerar ruído: {r.stderr}")


def _transcribe_file(wav_path: Path, use_rnnoise: bool) -> str:
    """Transcreve um arquivo WAV com ou sem RNNoise, retorna texto combinado."""
    with wave.open(str(wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        rate = wf.getframerate()
        pcm = wf.readframes(n_frames)

    # Converte para PCM s16le mono 16kHz se necessário
    if rate != 16000:
        pytest.skip(f"WAV com sample_rate {rate} != 16000")

    in_q = multiprocessing.Queue()
    out_q = multiprocessing.Queue()
    transcriber = TranscriberProcess(
        in_q, out_q, model_size="base", chunk_duration=7.0,
        language="pt", beam_size=1, temperature=0.0, vad_filter=True,
    )
    filter_obj = RNNoiseFilter(sample_rate=16000) if use_rnnoise else None

    texts: list[str] = []
    try:
        transcriber.start()
        # Envia em chunks de 480 samples (30ms)
        chunk_size = 480 * 2  # bytes
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i:i + chunk_size]
            if len(chunk) < 2:
                continue
            if filter_obj is not None:
                chunk = filter_obj.process_frame(chunk)
            in_q.put(chunk)
        # Aguarda processamento
        time.sleep(15)
        while True:
            try:
                item = out_q.get_nowait()
                if isinstance(item, dict) and item.get("text"):
                    texts.append(item["text"])
            except _q.Empty:
                break
    finally:
        transcriber.stop()
        transcriber.join(timeout=20)
        try:
            while True:
                item = out_q.get_nowait()
                if isinstance(item, dict) and item.get("text"):
                    texts.append(item["text"])
        except _q.Empty:
            pass
    return " ".join(texts)


class TestRNNoiseQualityReal:
    """T5.1–T5.5: integração real de RNNoise."""

    def setup_method(self):
        require_pipewire()
        require_pactl()
        require_espeak()
        require_pw_play()
        require_stt_model("base")

    def test_t52_rnnoise_does_not_worsen_transcription(self, tmp_path):
        """T5.2 (integração): guard-rail crítico.

        Compara nº de termos reconhecidos:
        - Transcrição de fixture com ruído (A3) SEM filtro
        - Transcrição da mesma fixture COM RNNoise

        Se a versão com filtro reconhecer MENOS termos, o teste FALHA.
        Esse é o guard-rail que evita regressão silenciosa: filtros
        agressivos (RNNoise/DeepFilterNet) podem piorar o WER do Whisper.
        """
        clean_wav = tmp_path / "clean.wav"
        noisy_wav = tmp_path / "noisy.wav"
        _generate_espeak_wav(REFERENCE_PHRASE, clean_wav)
        _generate_noisy_wav(clean_wav, noisy_wav)

        # Sem filtro
        text_no_filter = _transcribe_file(noisy_wav, use_rnnoise=False)
        # Com RNNoise
        text_with_filter = _transcribe_file(noisy_wav, use_rnnoise=True)

        n_no = _count_terms(text_no_filter)
        n_with = _count_terms(text_with_filter)

        # T5.2: versão com filtro NÃO pode reconhecer menos termos
        assert n_with >= n_no, (
            f"T5.2 FALHOU: RNNoise piorou a transcrição. "
            f"sem_filtro={n_no} com_filtro={n_with} "
            f"sem_filtro_text={text_no_filter!r} "
            f"com_filtro_text={text_with_filter!r}"
        )

    def test_t51_noise_reduction_measurable(self, tmp_path):
        """T5.1: SNR pós-RNNoise maior que SNR original (em trechos de silêncio)."""
        clean_wav = tmp_path / "clean.wav"
        noisy_wav = tmp_path / "noisy.wav"
        _generate_espeak_wav(REFERENCE_PHRASE, clean_wav)
        _generate_noisy_wav(clean_wav, noisy_wav)

        with wave.open(str(noisy_wav), "rb") as wf:
            pcm = wf.readframes(wf.getnframes())
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        # Pega os primeiros 0.5s como "silêncio" (antes da fala começar)
        silence_in = arr[: int(0.5 * 16000)]
        rms_in = float(np.sqrt(np.mean(silence_in ** 2)))

        # Aplica RNNoise
        filter_obj = RNNoiseFilter(sample_rate=16000)
        out = filter_obj.process_frame(pcm)
        out_arr = np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768.0
        silence_out = out_arr[: int(0.5 * 16000)]
        rms_out = float(np.sqrt(np.mean(silence_out ** 2)))

        # T5.1: ruído de silêncio deve ser menor após filtro
        assert rms_out <= rms_in, (
            f"T5.1: ruído aumentou após filtro: in={rms_in:.4f} out={rms_out:.4f}"
        )

    def test_t54_filtered_audio_same_duration(self, tmp_path):
        """T5.4: duração do áudio filtrado é idêntica à original (±5ms)."""
        clean_wav = tmp_path / "clean.wav"
        dur = _generate_espeak_wav(REFERENCE_PHRASE, clean_wav)
        with wave.open(str(clean_wav), "rb") as wf:
            pcm = wf.readframes(wf.getnframes())

        filter_obj = RNNoiseFilter(sample_rate=16000)
        out = filter_obj.process_frame(pcm)
        # Tamanho em bytes deve ser igual
        assert len(out) == len(pcm), (
            f"T5.4: tamanho diverge. in={len(pcm)} out={len(out)}"
        )

    def test_t55_clean_audio_no_artifacts(self, tmp_path):
        """T5.5: áudio já limpo processado por RNNoise não perde termos."""
        clean_wav = tmp_path / "clean.wav"
        _generate_espeak_wav(REFERENCE_PHRASE, clean_wav)

        text_no_filter = _transcribe_file(clean_wav, use_rnnoise=False)
        text_with_filter = _transcribe_file(clean_wav, use_rnnoise=True)

        n_no = _count_terms(text_no_filter)
        n_with = _count_terms(text_with_filter)
        # T5.5: versão filtrada deve reconhecer os mesmos termos (>=)
        assert n_with >= n_no, (
            f"T5.5 FALHOU: RNNoise introduziu distorção em áudio limpo. "
            f"sem_filtro={n_no} com_filtro={n_with}"
        )
