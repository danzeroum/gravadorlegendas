"""Transcrição de arquivo com separação de falantes (Frentes F e J).

Pipeline único usado pela CLI (``scripts/transcribe_file.py --diarize``) e
pela importação na interface: decodificar → transcrever com tempo por
palavra → diarizar → atribuir falante por palavra → agrupar em legendas.

Sem diarização disponível (extra ou token ausente), o arquivo é transcrito
mesmo assim, sem falantes, e o motivo fica em ``diarization_error`` — a
separação de vozes nunca impede a transcrição (a menos que o chamador peça
``require_diarization=True``, como a CLI com ``--diarize``).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import structlog

from src.audio.file_decode import decode_to_wav16k, wav_duration_s
from src.audio.models import CaptionSegment
from src.audio.speaker_assignment import Word, assign_words, group_segments
from src.config import settings

_logger = structlog.get_logger()

# Peso da transcrição na barra de progresso quando também há diarização.
_TRANSCRIBE_WEIGHT = 0.75

ProgressCallback = Callable[[float, str], None]


class TranscriptionCancelled(Exception):
    """O usuário cancelou a transcrição do arquivo."""


@dataclass
class FileTranscript:
    """Resultado da transcrição de um arquivo.

    Attributes:
        source: Caminho do arquivo original.
        duration_s: Duração do áudio.
        segments: Legendas; ``speaker`` preenchido quando ``diarized``.
        words: Palavras com o falante atribuído (``None`` = sem rótulo).
        diarized: True se a separação de falantes rodou.
        diarization_error: Motivo, se a separação não rodou.
        speakers: Rótulo → nome exibido (preenchido pela camada de rótulos).
    """

    source: str
    duration_s: float
    segments: list[CaptionSegment]
    words: list[tuple[Word, str | None]] = field(default_factory=list)
    diarized: bool = False
    diarization_error: str | None = None
    speakers: dict[str, str] = field(default_factory=dict)


def load_whisper(model_size: str, device: str = "auto"):
    """Carrega o WhisperModel usando o mesmo cache do app."""
    from faster_whisper import WhisperModel

    from src.audio.transcribe import WHISPER_DOWNLOAD_ROOT

    if device == "auto":
        device = "cpu"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device = "cuda"
        except Exception:
            pass
    return WhisperModel(model_size, device=device,
                        download_root=str(WHISPER_DOWNLOAD_ROOT))


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled()


def transcribe_audio_file(
    path: str | Path,
    *,
    model=None,
    model_size: str | None = None,
    device: str | None = None,
    language: str | None = "",
    beam_size: int | None = None,
    vad_filter: bool | None = None,
    diarize: bool = True,
    require_diarization: bool = False,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    diarizer=None,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> FileTranscript:
    """Transcreve ``path`` (mp3, m4a, mp4, ogg, opus, flac, webm, wav).

    Args:
        model: ``WhisperModel`` já carregado (senão carrega ``model_size``).
        language: Idioma do Whisper; ``""`` = ``settings.stt_language``;
            ``None`` = detecção automática.
        diarize: Tenta separar falantes.
        require_diarization: Falha (``DiarizationUnavailable``) em vez de
            seguir sem falantes.
        num_speakers / min_speakers / max_speakers: Dicas ao diarizador.
        diarizer: ``OfflineDiarizer`` (injeção para testes).
        on_progress: ``callback(fração 0..1, etapa)``.
        cancel: Evento; quando setado, interrompe com
            :class:`TranscriptionCancelled`.

    Raises:
        AudioDecodeError: arquivo ilegível.
        TranscriptionCancelled: cancelado pelo usuário.
    """
    from src.audio.offline_diarizer import DiarizationUnavailable, OfflineDiarizer

    def progress(fraction: float, stage: str) -> None:
        if on_progress is not None:
            on_progress(max(0.0, min(1.0, fraction)), stage)

    language = settings.stt_language if language == "" else language
    beam_size = settings.stt_beam_size if beam_size is None else beam_size
    vad_filter = settings.stt_vad_filter if vad_filter is None else vad_filter

    progress(0.0, "Lendo o arquivo…")
    wav = decode_to_wav16k(path)
    try:
        duration = wav_duration_s(wav)
        _check_cancel(cancel)

        diarization_error = None
        if diarize:
            diarizer = diarizer or OfflineDiarizer()
            try:
                diarizer.check_ready()
            except DiarizationUnavailable as e:
                if require_diarization:
                    raise
                diarize, diarization_error = False, str(e)

        if model is None:
            progress(0.0, "Carregando modelo de transcrição…")
            model = load_whisper(model_size or settings.stt_model,
                                 device or settings.stt_device)
        _check_cancel(cancel)

        weight = _TRANSCRIBE_WEIGHT if diarize else 1.0
        progress(0.0, "Transcrevendo…")
        raw_segments, _info = model.transcribe(
            str(wav), language=language, task="transcribe",
            beam_size=beam_size, temperature=0.0, vad_filter=vad_filter,
            word_timestamps=diarize,
        )
        plain: list[CaptionSegment] = []
        words: list[Word] = []
        for seg in raw_segments:
            _check_cancel(cancel)
            text = (seg.text or "").strip()
            if not text or seg.end <= seg.start:
                continue
            plain.append(CaptionSegment(float(seg.start), float(seg.end), text))
            seg_words = [
                Word(float(w.start), float(w.end), w.word.strip())
                for w in (getattr(seg, "words", None) or [])
                if (w.word or "").strip() and w.end > w.start
            ]
            # Sem tempo por palavra, o segmento inteiro vira uma "palavra".
            words.extend(seg_words or [Word(float(seg.start), float(seg.end), text)])
            if duration > 0:
                progress(weight * float(seg.end) / duration, "Transcrevendo…")

        result = FileTranscript(source=str(path), duration_s=duration,
                                segments=plain,
                                diarization_error=diarization_error)
        if not diarize or not plain:
            progress(1.0, "Concluído")
            return result

        _check_cancel(cancel)
        progress(weight, "Separando vozes…")
        try:
            turns = diarizer.diarize(str(wav), num_speakers=num_speakers,
                                     min_speakers=min_speakers,
                                     max_speakers=max_speakers)
        except Exception as e:
            if require_diarization:
                raise
            _logger.error("file_diarization_failed", error=str(e))
            result.diarization_error = f"Falha ao separar falantes: {e}"
            progress(1.0, "Concluído")
            return result
        _check_cancel(cancel)

        assigned = assign_words(words, turns)
        result.words = assigned
        result.segments = group_segments(assigned)
        result.diarized = True
        progress(1.0, "Concluído")
        _logger.info("file_transcribed", duration_s=round(duration, 1),
                     segments=len(result.segments),
                     speakers=len({s.speaker for s in result.segments if s.speaker}))
        return result
    finally:
        Path(wav).unlink(missing_ok=True)
