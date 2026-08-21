"""Testes unitários para SubtitleExporter (Frente D).

Validam formatação SRT/VTT, encoding UTF-8, sincronismo de timestamps
e o guard-rail crítico **T6.6** (sem legenda alucinada em silêncio).

Os testes de integração T6.1–T6.6 (com transcrição real via Whisper
sobre fixture A2) estão em ``tests/integration/test_export_srt_vtt_real.py``
e fazem skip automático em ambientes sem PipeWire/pactl/Whisper.
"""
from __future__ import annotations

import os
import re

import pytest

from src.audio.models import CaptionSegment
from src.storage.subtitle_exporter import (
    SubtitleExporter,
    _format_srt_timestamp,
    _format_vtt_timestamp,
)


class TestTimestampFormatting:
    """Testes de formatação de timestamp."""

    def test_srt_format_uses_comma(self):
        """SRT usa vírgula como separador de ms."""
        assert _format_srt_timestamp(0.0) == "00:00:00,000"
        assert _format_srt_timestamp(1.5) == "00:00:01,500"
        assert _format_srt_timestamp(3661.234) == "01:01:01,234"

    def test_vtt_format_uses_dot(self):
        """VTT usa ponto como separador de ms."""
        assert _format_vtt_timestamp(0.0) == "00:00:00.000"
        assert _format_vtt_timestamp(1.5) == "00:00:01.500"
        assert _format_vtt_timestamp(3661.234) == "01:01:01.234"

    def test_negative_clamped_to_zero(self):
        """Timestamps negativos viram 0."""
        assert _format_srt_timestamp(-1.0) == "00:00:00,000"
        assert _format_vtt_timestamp(-1.0) == "00:00:00.000"

    def test_rounding_to_milliseconds(self):
        """Ms é arredondado (não truncado)."""
        # 1.2349s -> 1234.9ms -> arredondado para 1235
        assert _format_srt_timestamp(1.2349) == "00:00:01,235"
        # 1.2341s -> 1234.1ms -> arredondado para 1234
        assert _format_srt_timestamp(1.2341) == "00:00:01,234"

    def test_hours_always_two_digits(self):
        """Horas sempre com 2 dígitos."""
        assert _format_srt_timestamp(3600 * 5).startswith("05:")
        assert _format_srt_timestamp(3600 * 12).startswith("12:")


class TestSubtitleExporterSRT:
    """Testes de geração SRT."""

    def test_srt_basic_structure(self):
        """T6.1 (unitário): formato SRT tem numeração sequencial + timestamps."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="Primeiro bloco"),
            CaptionSegment(start=2.5, end=4.5, text="Segundo bloco"),
        ]
        srt = exporter.to_srt(segments)
        # Numeração sequencial 1, 2
        assert re.search(r"^1\n", srt, re.MULTILINE)
        assert re.search(r"^2\n", srt, re.MULTILINE)
        # Formato de timestamp SRT com vírgula e "-->"
        assert "00:00:00,000 --> 00:00:02,000" in srt
        assert "00:00:02,500 --> 00:00:04,500" in srt

    def test_srt_no_overlap_between_blocks(self):
        """T6.1: blocos consecutivos não se sobrepõem."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="A"),
            CaptionSegment(start=2.0, end=4.0, text="B"),
            CaptionSegment(start=4.0, end=6.0, text="C"),
        ]
        srt = exporter.to_srt(segments)
        # Extrai todos os timestamps
        timestamps = re.findall(
            r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})",
            srt,
        )
        assert len(timestamps) == 3
        # Converte para segundos para validar não-sobreposição
        def to_sec(ts):
            h, m, s_ms = ts.split(":")
            s, ms = s_ms.split(",")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

        for i in range(len(timestamps) - 1):
            end_current = to_sec(timestamps[i][1])
            start_next = to_sec(timestamps[i + 1][0])
            assert start_next >= end_current, (
                f"Sobreposição entre bloco {i+1} e {i+2}: "
                f"end={end_current} start_next={start_next}"
            )

    def test_srt_empty_segments_returns_empty_string(self):
        """Lista vazia gera string vazia (sem cabeçalho inútil)."""
        exporter = SubtitleExporter()
        assert exporter.to_srt([]) == ""

    def test_srt_save_to_file(self, tmp_path):
        """T6.5 (unitário): arquivo SRT é salvo em UTF-8."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="Texto com acentuação: ção, ã, é"),
        ]
        path = str(tmp_path / "out.srt")
        exporter.save_srt(segments, path)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Texto com acentuação: ção, ã, é" in content


class TestSubtitleExporterVTT:
    """Testes de geração WebVTT."""

    def test_vtt_has_webvtt_header(self):
        """T6.2 (unitário): VTT começa com WEBVTT."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="Olá"),
        ]
        vtt = exporter.to_vtt(segments)
        assert vtt.startswith("WEBVTT")
        # E tem uma linha em branco após o cabeçalho
        assert vtt.startswith("WEBVTT\n")

    def test_vtt_uses_dot_in_timestamps(self):
        """T6.2: VTT usa ponto (não vírgula) nos timestamps."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.5, text="Teste"),
        ]
        vtt = exporter.to_vtt(segments)
        assert "00:00:00.000 --> 00:00:02.500" in vtt
        # Garantia extra: NÃO deve ter vírgula nos timestamps
        # (cabeçalho WEBVTT também não tem vírgula em timestamps)
        timestamp_lines = [
            line for line in vtt.split("\n") if "-->" in line
        ]
        for line in timestamp_lines:
            # Timestamp VTT não deve ter vírgula (apenas ponto)
            assert "," not in line.split("-->")[0], (
                f"VTT tem vírgula no timestamp: {line}"
            )

    def test_vtt_empty_segments_returns_just_header(self):
        """Lista vazia: VTT tem só o cabeçalho."""
        exporter = SubtitleExporter()
        vtt = exporter.to_vtt([])
        assert vtt.strip() == "WEBVTT"

    def test_vtt_save_to_file(self, tmp_path):
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="Teste VTT"),
        ]
        path = str(tmp_path / "out.vtt")
        exporter.save_vtt(segments, path)
        assert os.path.exists(path)
        with open(path, "rb") as f:
            raw = f.read()
        # Validar UTF-8
        raw.decode("utf-8")  # não lança exceção = UTF-8 válido
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "WEBVTT" in content
        assert "Teste VTT" in content


class TestSubtitleExporterT66GuardRail:
    """Guard-rail T6.6 (unitário em memória): sem legenda alucinada em silêncio.

    Cenário simulado: sessão com fala → 5s de silêncio → fala novamente.
    Os segmentos vazios (que viriam de silêncio transcrito pelo Whisper)
    são filtrados pelo exportador, e o resultado não contém blocos
    vazios nem com texto inválido.

    A versão de integração (T6.6 com Whisper real sobre fixture A6
    "silêncio_puro.wav") está em tests/integration/test_export_srt_vtt_real.py.
    """

    def test_t66_empty_text_segments_filtered_out(self):
        """T6.6: segmentos com texto vazio não geram blocos."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="Primeira fala"),
            CaptionSegment(start=2.0, end=7.0, text=""),  # silêncio de 5s
            CaptionSegment(start=7.0, end=9.0, text="Segunda fala"),
        ]
        srt = exporter.to_srt(segments)
        # Deve ter só 2 blocos (não 3)
        blocks = [b for b in srt.split("\n\n") if b.strip()]
        assert len(blocks) == 2, (
            f"Esperado 2 blocos (silêncio filtrado), obtido {len(blocks)}: {srt}"
        )
        # E o conteúdo dos 2 blocos deve ser o texto das falas
        assert "Primeira fala" in srt
        assert "Segunda fala" in srt

    def test_t66_whitespace_only_text_filtered_out(self):
        """T6.6: segmentos com só whitespace também são filtrados."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=1.0, text="   "),  # só espaços
            CaptionSegment(start=1.0, end=2.0, text="Fala real"),
        ]
        srt = exporter.to_srt(segments)
        blocks = [b for b in srt.split("\n\n") if b.strip()]
        assert len(blocks) == 1
        assert "Fala real" in srt

    def test_t66_zero_duration_segments_filtered_out(self):
        """Segmentos com start == end (instantâneos) são filtrados."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=0.0, text="Instantâneo"),  # inválido
            CaptionSegment(start=1.0, end=2.0, text="Válido"),
        ]
        srt = exporter.to_srt(segments)
        blocks = [b for b in srt.split("\n\n") if b.strip()]
        assert len(blocks) == 1
        assert "Válido" in srt
        assert "Instantâneo" not in srt

    def test_t66_negative_start_filtered_out(self):
        """Segmentos com start negativo são filtrados."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=-1.0, end=1.0, text="Inválido"),
            CaptionSegment(start=0.0, end=2.0, text="Válido"),
        ]
        srt = exporter.to_srt(segments)
        assert "Válido" in srt
        assert "Inválido" not in srt

    def test_t66_pure_silence_session_produces_no_file_content(self):
        """T6.6 (extremo): sessão inteira de silêncio não produz legenda."""
        exporter = SubtitleExporter()
        # Sessão de 10s com 5 segmentos vazios (simulando Whisper alucinando
        # em silêncio puro — exatamente o cenário que o guard-rail protege).
        segments = [
            CaptionSegment(start=0.0, end=2.0, text=""),
            CaptionSegment(start=2.0, end=4.0, text=""),
            CaptionSegment(start=4.0, end=6.0, text=""),
            CaptionSegment(start=6.0, end=8.0, text=""),
            CaptionSegment(start=8.0, end=10.0, text=""),
        ]
        srt = exporter.to_srt(segments)
        vtt = exporter.to_vtt(segments)
        # SRT deve ser string vazia
        assert srt == ""
        # VTT deve ter só o cabeçalho (sem blocos)
        assert vtt.strip() == "WEBVTT"


class TestSubtitleExporterSpecialChars:
    """T6.5: caracteres especiais e acentuação preservados."""

    def test_portuguese_accents_preserved(self):
        """T6.5: acentos portugueses (á, ç, ã, é, í, ó, ú) preservados."""
        exporter = SubtitleExporter()
        text = "não é possível, então vamos à reunião"
        segments = [CaptionSegment(start=0.0, end=2.0, text=text)]
        srt = exporter.to_srt(segments)
        assert text in srt

    def test_em_dash_and_quotes_preserved(self):
        """T6.5: travessão, aspas, ponto-e-vírgula preservados."""
        exporter = SubtitleExporter()
        text = 'Ela disse: "olá" — e saiu; fim.'
        segments = [CaptionSegment(start=0.0, end=2.0, text=text)]
        srt = exporter.to_srt(segments)
        assert text in srt

    def test_utf8_file_no_mojibake(self, tmp_path):
        """T6.5: arquivo salvo em UTF-8 sem mojibake."""
        exporter = SubtitleExporter()
        text = "Olá — café — résumé — façade — über"
        segments = [CaptionSegment(start=0.0, end=2.0, text=text)]
        path = str(tmp_path / "special.srt")
        exporter.save_srt(segments, path)
        # Lê como UTF-8 e verifica
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert text in content
        # Lê como bytes e valida UTF-8
        with open(path, "rb") as f:
            raw = f.read()
        raw.decode("utf-8")  # não lança = válido

    def test_all_segments_text_preserved_in_srt(self):
        """T6.4 (unitário): nenhum texto perdido entre segmentos."""
        exporter = SubtitleExporter()
        segments = [
            CaptionSegment(start=0.0, end=2.0, text="primeiro"),
            CaptionSegment(start=2.5, end=4.5, text="segundo"),
            CaptionSegment(start=5.0, end=7.0, text="terceiro"),
        ]
        srt = exporter.to_srt(segments)
        # Todos os textos devem estar presentes
        for expected in ["primeiro", "segundo", "terceiro"]:
            assert expected in srt, f"Texto perdido: {expected}"
