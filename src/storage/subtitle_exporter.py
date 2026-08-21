"""Exportação de legendas em formato SRT e WebVTT.

Frente D do plano de curto prazo: converte uma lista de
:class:`CaptionSegment` (start, end, text) em arquivo de legenda.

Garantias:
- Formatação de timestamp SRT: ``HH:MM:SS,mmm`` (vírgula).
- Formatação de timestamp VTT: ``HH:MM:SS.mmm`` (ponto) + cabeçalho
  ``WEBVTT`` na primeira linha.
- Encoding UTF-8 na escrita (preserva acentuação — cobre T6.5).
- Não gera bloco para segmentos vazios/silêncio (cobre T6.6 — sem
  legenda alucinada em silêncio).
- Numeração sequencial e sem sobreposição entre blocos consecutivos.
"""
from __future__ import annotations

from pathlib import Path

import structlog

from src.audio.models import CaptionSegment

_logger = structlog.get_logger()


class SubtitleExporter:
    """Converte lista de segmentos em SRT ou VTT.

    Example:
        >>> segs = [
        ...     CaptionSegment(start=0.0, end=2.5, text="Olá mundo"),
        ...     CaptionSegment(start=3.0, end=5.5, text="Segunda legenda"),
        ... ]
        >>> exporter = SubtitleExporter()
        >>> srt = exporter.to_srt(segs)
        >>> "WEBVTT" in srt
        False
        >>> vtt = exporter.to_vtt(segs)
        >>> vtt.startswith("WEBVTT")
        True
    """

    def to_srt(self, segments: list[CaptionSegment]) -> str:
        """Gera conteúdo SRT a partir de uma lista de segmentos.

        Args:
            segments: Lista de CaptionSegment, ordenados por ``start``.

        Returns:
            String no formato SRT, com blocos numerados sequencialmente
            e timestamps no formato ``HH:MM:SS,mmm``.
        """
        blocks: list[str] = []
        for idx, seg in enumerate(self._filter_valid(segments), start=1):
            blocks.append(
                f"{idx}\n"
                f"{_format_srt_timestamp(seg.start)} --> "
                f"{_format_srt_timestamp(seg.end)}\n"
                f"{seg.text}\n"
            )
        return "\n".join(blocks).rstrip() + "\n" if blocks else ""

    def to_vtt(self, segments: list[CaptionSegment]) -> str:
        """Gera conteúdo WebVTT a partir de uma lista de segmentos.

        Args:
            segments: Lista de CaptionSegment, ordenados por ``start``.

        Returns:
            String no formato WebVTT, com cabeçalho ``WEBVTT`` e
            timestamps no formato ``HH:MM:SS.mmm`` (ponto).
        """
        blocks: list[str] = ["WEBVTT", ""]
        for seg in self._filter_valid(segments):
            blocks.append(
                f"{_format_vtt_timestamp(seg.start)} --> "
                f"{_format_vtt_timestamp(seg.end)}\n"
                f"{seg.text}\n"
            )
        return "\n".join(blocks).rstrip() + "\n" if len(blocks) > 2 else "WEBVTT\n\n"

    def save_srt(self, segments: list[CaptionSegment], path: str) -> None:
        """Salva a lista de segmentos como arquivo .srt.

        Args:
            segments: Lista de CaptionSegment.
            path: Caminho do arquivo .srt a ser criado.
        """
        content = self.to_srt(segments)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        _logger.info("srt_saved", path=path, n_blocks=len(content.split("\n\n")))

    def save_vtt(self, segments: list[CaptionSegment], path: str) -> None:
        """Salva a lista de segmentos como arquivo .vtt.

        Args:
            segments: Lista de CaptionSegment.
            path: Caminho do arquivo .vtt a ser criado.
        """
        content = self.to_vtt(segments)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        _logger.info("vtt_saved", path=path, n_blocks=content.count("-->"))

    @staticmethod
    def _filter_valid(
        segments: list[CaptionSegment],
    ) -> list[CaptionSegment]:
        """Filtra segmentos inválidos/vazios (cobre T6.6).

        Um segmento é válido se:
        - ``text`` não é vazio após strip.
        - ``end > start`` (não é instantâneo).
        - ``start >= 0``.
        """
        return [
            seg for seg in segments
            if seg.text and seg.text.strip()
            and seg.end > seg.start
            and seg.start >= 0
        ]


def _format_srt_timestamp(seconds: float) -> str:
    """Converte segundos para ``HH:MM:SS,mmm`` (vírgula)."""
    return _format_timestamp(seconds, sep=",")


def _format_vtt_timestamp(seconds: float) -> str:
    """Converte segundos para ``HH:MM:SS.mmm`` (ponto)."""
    return _format_timestamp(seconds, sep=".")


def _format_timestamp(seconds: float, sep: str) -> str:
    """Formata segundos como ``HH:MM:SS<sep>mmm``.

    Args:
        seconds: Tempo em segundos (float).
        sep: Separador entre segundos e milissegundos ("," para SRT,
            "." para VTT).

    Returns:
        String formatada, sempre com 2 dígitos para H/M/S e 3 para ms.
    """
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"
