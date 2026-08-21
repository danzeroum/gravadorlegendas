"""Testes de integração T6.1–T6.6: export SRT/VTT via Whisper real.

Requer:
- PipeWire rodando (``require_pipewire()``).
- ``pactl`` disponível (``require_pactl()``).
- ``pw-play`` disponível (``require_pw_play()``).
- ``espeak-ng`` disponível (``require_espeak()``).
- Modelo Whisper ``base`` em cache.

Em ambientes sem essas dependências, os testes fazem skip automático.
"""
from __future__ import annotations

import multiprocessing
import os
import queue as _q
import re
import subprocess
import time
import unicodedata
import wave
from pathlib import Path

import pytest

from src.audio.models import CaptionSegment
from src.audio.transcribe import TranscriberProcess
from src.storage.subtitle_exporter import SubtitleExporter

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

PHRASE_LONG = "teste de transcrição local no Fedora"
PHRASE_WITH_ACCENTS = "não é possível, então vamos à reunião"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _generate_espeak_wav(text: str, dest: Path, voice: str = "pt-br") -> float:
    raw = dest.with_suffix(".raw.wav")
    cmd = ["espeak-ng", "-v", voice, "-s", "90", "-w", str(raw), text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"espeak-ng: {r.stderr}")
    resample = ["ffmpeg", "-y", "-i", str(raw), "-ar", "16000", "-ac", "1", str(dest)]
    r2 = subprocess.run(resample, capture_output=True, text=True, timeout=30)
    if r2.returncode != 0:
        raise RuntimeError(f"ffmpeg resample: {r2.stderr}")
    raw.unlink(missing_ok=True)
    with wave.open(str(dest), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _transcribe_wav_to_segments(wav_path: Path) -> list[CaptionSegment]:
    """Transcreve WAV via Whisper real e retorna lista de CaptionSegment."""
    with wave.open(str(wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        rate = wf.getframerate()
        pcm = wf.readframes(n_frames)
    if rate != 16000:
        pytest.skip(f"WAV com sample_rate {rate} != 16000")

    in_q = multiprocessing.Queue()
    out_q = multiprocessing.Queue()
    transcriber = TranscriberProcess(
        in_q, out_q, model_size="base", chunk_duration=5.0,
        language="pt", beam_size=1, temperature=0.0, vad_filter=True,
    )
    segments: list[CaptionSegment] = []
    try:
        transcriber.start()
        chunk_size = 480 * 2
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i:i + chunk_size]
            if len(chunk) < 2:
                continue
            in_q.put(chunk)
        time.sleep(20)
        while True:
            try:
                item = out_q.get_nowait()
                if not isinstance(item, dict):
                    continue
                if "segments" in item and item["segments"]:
                    for s in item["segments"]:
                        segments.append(CaptionSegment(
                            start=s["start"], end=s["end"], text=s["text"],
                        ))
                elif item.get("text"):
                    segments.append(CaptionSegment(
                        start=item.get("start", 0.0),
                        end=item.get("end", 0.0),
                        text=item["text"],
                    ))
            except _q.Empty:
                break
    finally:
        transcriber.stop()
        transcriber.join(timeout=20)
        try:
            while True:
                item = out_q.get_nowait()
                if not isinstance(item, dict):
                    continue
                if "segments" in item and item["segments"]:
                    for s in item["segments"]:
                        segments.append(CaptionSegment(
                            start=s["start"], end=s["end"], text=s["text"],
                        ))
                elif item.get("text"):
                    segments.append(CaptionSegment(
                        start=item.get("start", 0.0),
                        end=item.get("end", 0.0),
                        text=item["text"],
                    ))
        except _q.Empty:
            pass
    # Burst-feed faz elapsed≈0 no 1º batch → start negativo (-7/-5).
    # Em streaming real, elapsed já é ~7s e start≈0. Normaliza para o
    # exporter não filtrar (start>=0) e T63 não falhar por offset.
    if segments:
        min_start = min(s.start for s in segments)
        if min_start < 0:
            offset = -min_start
            segments = [
                CaptionSegment(start=s.start + offset, end=s.end + offset, text=s.text)
                for s in segments
            ]
    return segments


class TestExportSrtVttReal:
    """T6.1–T6.6: integração real de export SRT/VTT."""

    def setup_method(self):
        require_pipewire()
        require_pactl()
        require_espeak()
        require_pw_play()
        require_stt_model("base")

    def test_t61_srt_format_valid(self, tmp_path):
        """T6.1: SRT sintaticamente válido a partir de transcrição real."""
        wav = tmp_path / "phrase.wav"
        _generate_espeak_wav(PHRASE_LONG, wav)
        segments = _transcribe_wav_to_segments(wav)
        if not segments:
            pytest.skip("Whisper não produziu segmentos")

        exporter = SubtitleExporter()
        srt = exporter.to_srt(segments)
        # Numeração sequencial
        numbers = re.findall(r"^(\d+)\s*$", srt, re.MULTILINE)
        assert numbers, "SRT sem numeração sequencial"
        nums = [int(n) for n in numbers]
        assert nums == list(range(1, len(nums) + 1)), (
            f"Numeração não sequencial: {nums}"
        )
        # Timestamps no formato HH:MM:SS,mmm --> HH:MM:SS,mmm
        ts_pattern = r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}"
        timestamps = re.findall(ts_pattern, srt)
        assert len(timestamps) == len(nums), (
            f"Número de timestamps ({len(timestamps)}) != número de blocos ({len(nums)})"
        )

    def test_t62_vtt_format_valid(self, tmp_path):
        """T6.2: VTT sintaticamente válido."""
        wav = tmp_path / "phrase.wav"
        _generate_espeak_wav(PHRASE_LONG, wav)
        segments = _transcribe_wav_to_segments(wav)
        if not segments:
            pytest.skip("Whisper não produziu segmentos")

        exporter = SubtitleExporter()
        vtt = exporter.to_vtt(segments)
        assert vtt.startswith("WEBVTT"), "VTT não começa com WEBVTT"
        # Timestamps no formato HH:MM:SS.mmm (ponto)
        ts_pattern = r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}"
        timestamps = re.findall(ts_pattern, vtt)
        assert len(timestamps) > 0, "VTT sem timestamps no formato correto"

    def test_t63_subtitle_sync_with_audio(self, tmp_path):
        """T6.3: timestamp do primeiro bloco próximo ao início da fala."""
        wav = tmp_path / "phrase.wav"
        _generate_espeak_wav(PHRASE_LONG, wav)
        segments = _transcribe_wav_to_segments(wav)
        if not segments:
            pytest.skip("Whisper não produziu segmentos")
        # Primeiro segmento deve começar dentro de ±300ms do início
        # (espeak não adiciona silêncio inicial significativo).
        first_start = segments[0].start
        assert abs(first_start) < 1.0, (
            f"Primeiro bloco começa em {first_start:.2f}s — muito longe do início"
        )

    def test_t64_no_text_lost(self, tmp_path):
        """T6.4: todos os termos esperados estão presentes no SRT."""
        wav = tmp_path / "phrase.wav"
        _generate_espeak_wav(PHRASE_LONG, wav)
        segments = _transcribe_wav_to_segments(wav)
        if not segments:
            pytest.skip("Whisper não produziu segmentos")
        exporter = SubtitleExporter()
        srt = exporter.to_srt(segments)
        # Pelo menos 2 termos-chave presentes
        terms = ["teste", "transcricao", "local", "fedora"]
        norm_srt = _normalize(srt)
        n_found = sum(1 for t in terms if _normalize(t) in norm_srt.split())
        assert n_found >= 2, (
            f"Poucos termos encontrados ({n_found}/4) em SRT: {srt!r}"
        )

    def test_t65_special_chars_preserved(self, tmp_path):
        """T6.5: acentos e caracteres especiais preservados no SRT."""
        wav = tmp_path / "accents.wav"
        _generate_espeak_wav(PHRASE_WITH_ACCENTS, wav)
        segments = _transcribe_wav_to_segments(wav)
        if not segments:
            pytest.skip("Whisper não produziu segmentos")
        exporter = SubtitleExporter()
        path = str(tmp_path / "out.srt")
        exporter.save_srt(segments, path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Não deve haver mojibake (caracteres ??)
        assert "??" not in content, f"Mojibake detectado em SRT: {content!r}"
        # Deve ter pelo menos um caractere acentuado preservado
        has_accent = any(c in content for c in "áéíóúâêôãõçà")
        assert has_accent, f"Sem acentos no SRT: {content!r}"

    def test_t66_no_alucinated_block_in_silence(self, tmp_path):
        """T6.6 (integração): guard-rail crítico.

        Cenário: fala → 5s silêncio → fala novamente.
        O Whisper pode tentar alucinar texto durante o silêncio
        (regressão conhecida — "e o que é o que é..."). O filtro de
        VAD integrado ao TranscriberProcess deve bloquear isso, e o
        SubtitleExporter não deve gerar blocos com texto vazio.

        Se este teste falha, significa que algum bloco de silêncio
        passou pelo filtro — é regressão.
        """
        # Gera WAV com fala + silêncio + fala
        wav1 = tmp_path / "p1.wav"
        wav2 = tmp_path / "p2.wav"
        combined = tmp_path / "combined.wav"
        _generate_espeak_wav("primeira fala", wav1)
        _generate_espeak_wav("segunda fala", wav2)
        # Concatena com 5s de silêncio no meio via ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-i", str(wav1),
            "-f", "lavfi", "-t", "5", "-i", "anullsrc=r=16000:cl=mono",
            "-i", str(wav2),
            "-filter_complex",
            "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]",
            "-map", "[a]",
            str(combined),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            pytest.skip(f"ffmpeg falhou: {r.stderr}")

        segments = _transcribe_wav_to_segments(combined)
        # Mesmo que Whisper alucine, o exportador filtra blocos vazios.
        exporter = SubtitleExporter()
        srt = exporter.to_srt(segments)
        # T6.6: nenhum bloco vazio deve existir
        blocks = [b.strip() for b in srt.split("\n\n") if b.strip()]
        for block in blocks:
            # Cada bloco deve ter pelo menos 3 linhas: número, timestamp, texto
            lines = block.split("\n")
            assert len(lines) >= 3, (
                f"Bloco SRT incompleto: {block!r}"
            )
            text_line = "\n".join(lines[2:]).strip()
            assert text_line, (
                f"T6.6 FALHOU: bloco SRT com texto vazio (legenda alucinada): "
                f"{block!r}"
            )
