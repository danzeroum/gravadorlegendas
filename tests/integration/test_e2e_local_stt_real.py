"""Testes de integração REAIS do pipeline de STT local (faster-whisper).

Exigem:
- Modelo Whisper já baixado em ~/.cache/gravador/audio/whisper/<size>/
- faster-whisper instalado (pip install -e ".[audio]")
- CPU funcional (ou GPU NVIDIA se STT_DEVICE=cuda)

NÃO usam rede. NÃO baixam modelos automaticamente.

Marcadores:
    @pytest.mark.integration
    @pytest.mark.requires_stt_model

Rodar:
    pytest -q -m "integration and requires_stt_model"
"""
from __future__ import annotations

import os
import struct
import time
from pathlib import Path

import pytest

from tests.integration.conftest import (
    WHISPER_DOWNLOAD_ROOT,
    fixture_sha256,
    generate_sine_wave_pcm16,
    require_stt_model,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_stt_model,
]


class TestLocalSTTReal:
    """Validação real da transcrição local com faster-whisper."""

    def setup_method(self):
        """Pula se modelo Whisper não está em cache."""
        require_stt_model("base")

    # ------------------------------------------------------------------
    # E2E-09: Transcrição local
    # ------------------------------------------------------------------

    def test_e2e_09_transcription_produces_text(self):
        """E2E-09: Transcrição produz texto não vazio a partir de áudio.

        ATENÇÃO: Este teste valida que o pipeline STT funciona, mas
        NÃO valida a transcrição de fala real — áudio sintético (onda
        senoidal) produz texto vazio ou ruído. Para validar fala real,
        é necessário fornecer uma fixture WAV com frase conhecida.

        Para uma validação E2E-09 completa, siga o roteiro manual em
        VALIDATION_STATUS.md ou forneça uma fixture WAV com frase
        de teste (ex: "Olá, este é um teste de transcrição.").
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            pytest.skip(f"faster-whisper não instalado: {e}")

        # Carrega modelo do cache (mesmo cache do app e do setup)
        try:
            model = WhisperModel("base", device="cpu", download_root=str(WHISPER_DOWNLOAD_ROOT))
        except Exception as e:
            pytest.skip(f"Não foi possível carregar modelo: {e}")

        # Gera áudio sintético (não é fala — apenas valida o pipeline)
        audio_bytes = generate_sine_wave_pcm16(duration_s=2.0, frequency=440.0)
        # Converte para numpy float32 (formato esperado pelo faster-whisper)
        import numpy as np
        audio_array = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )

        # Transcreve
        start = time.monotonic()
        try:
            segments, info = model.transcribe(audio_array, language="pt")
            segments_list = list(segments)
        except Exception as e:
            pytest.fail(f"Transcrição falhou: {e}")
        elapsed = time.monotonic() - start

        # Valida que o pipeline não quebrou (mesmo que texto seja vazio,
        # porque áudio sintético não é fala reconhecível)
        assert info is not None
        assert elapsed > 0
        # Para validar texto não vazio, é necessário áudio de fala real.
        # Registramos no log do teste para evidência.
        text = " ".join(seg.text for seg in segments_list).strip()
        # Não assertamos texto não vazio — onda senoidal não é fala.
        # Apenas registramos para inspeção manual.
        print(f"\n[STT] Áudio sintético -> texto: {text!r} (elapsed={elapsed:.2f}s)")

    def test_transcriber_process_lifecycle(self):
        """Valida ciclo de vida do TranscriberProcess (sem áudio real)."""
        try:
            from src.audio.transcribe import TranscriberProcess
        except ImportError as e:
            pytest.skip(f"TranscriberProcess indisponível: {e}")

        import multiprocessing
        in_q = multiprocessing.Queue()
        out_q = multiprocessing.Queue()

        proc = TranscriberProcess(in_q, out_q, model_size="base")
        try:
            proc.start()
            assert proc.is_alive()
            # Envia sentinela para parar
            proc.stop()
            proc.join(timeout=10)
            assert not proc.is_alive(), "Processo não terminou em 10s"
        except Exception:
            proc.stop()
            proc.join(timeout=5)
            raise

    def test_synthetic_fixture_hash_deterministic(self):
        """Confere que a fixture sintética tem hash determinístico."""
        data1 = generate_sine_wave_pcm16(duration_s=1.0, frequency=440.0)
        data2 = generate_sine_wave_pcm16(duration_s=1.0, frequency=440.0)
        h1 = fixture_sha256(data1)
        h2 = fixture_sha256(data2)
        assert h1 == h2, "Hashes diferentes para mesma fixture — não determinístico"
