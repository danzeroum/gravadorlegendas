"""Transcreve arquivos de áudio já gravados e gera legendas (.txt/.srt/.vtt).

Útil para reprocessar os ``.wav`` de ``data/recordings`` (ex.: gravados com
``RECORD_RAW_AUDIO=true``) quando a sessão não deixou legendas, ou para
refazer a transcrição com um modelo melhor.

Os arquivos de saída são gravados ao lado de cada ``.wav``, com o mesmo nome
base: ``reuniao_mic.wav`` → ``reuniao_mic.txt``, ``.srt`` e ``.vtt``.

Uso:
    python scripts/transcribe_file.py data/recordings/reuniao_mic.wav
    python scripts/transcribe_file.py data/recordings            # todos os .wav
    python scripts/transcribe_file.py arquivo.wav --model small --beam-size 5
    python scripts/transcribe_file.py data/recordings --force    # sobrescreve
    python scripts/transcribe_file.py audio_celular.m4a --diarize          # separa falantes
    python scripts/transcribe_file.py reuniao.mp4 --diarize --num-speakers 4
    python scripts/transcribe_file.py reuniao.mp3 --diarize --speaker-map nomes.json

Os padrões de modelo, idioma, beam e VAD vêm do ``.env`` (``STT_MODEL``,
``STT_LANGUAGE``, ``STT_BEAM_SIZE``, ``STT_VAD_FILTER``), os mesmos da
transcrição ao vivo. Para fala humana natural, ``--model small --beam-size 5``
costuma dar resultado melhor (mais lento).

``--diarize`` separa os falantes pela voz (pyannote.audio; exige o extra
``.[diarization]`` e token Hugging Face) e atribui cada palavra a um falante;
as legendas saem como ``[SPEAKER_00] texto``. ``--speaker-map`` troca os
rótulos por nomes: JSON ``{"SPEAKER_00": "Juliana"}`` ou o formato do painel
Falantes (``{"SPEAKER_00": {"name": "Juliana", "color": "..."}}``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.models import CaptionSegment  # noqa: E402
from src.config import settings  # noqa: E402
from src.storage.subtitle_exporter import SubtitleExporter  # noqa: E402

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}


def collect_inputs(paths: list[str]) -> list[Path]:
    """Expande arquivos/diretórios em uma lista ordenada de arquivos de áudio."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(
                sorted(f for f in p.iterdir()
                       if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
            )
        elif p.is_file():
            files.append(p)
        else:
            print(f"⚠️  Não encontrado: {p}", file=sys.stderr)
    return files


def load_model(model_size: str, device: str):
    """Carrega o WhisperModel usando o mesmo cache do app."""
    from src.audio.file_pipeline import load_whisper
    return load_whisper(model_size, device)


def load_speaker_map(path: str | None) -> dict[str, str]:
    """Lê ``--speaker-map``: ``{rótulo: nome}`` ou ``{rótulo: {name, color}}``."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        str(k): (v.get("name", "") if isinstance(v, dict) else str(v))
        for k, v in data.items()
    }


def transcribe(model, audio_path: Path, *, language: str | None,
               beam_size: int, vad_filter: bool) -> list[CaptionSegment]:
    """Transcreve um arquivo inteiro e devolve os segmentos com timestamp."""
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        task="transcribe",
        beam_size=beam_size,
        temperature=0.0,
        vad_filter=vad_filter,
    )
    result: list[CaptionSegment] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text or seg.end <= seg.start:
            continue
        result.append(CaptionSegment(start=float(seg.start),
                                     end=float(seg.end), text=text))
        print(f"   [{_fmt(seg.start)}] {text}", flush=True)
    return result


def transcribe_with_speakers(model, diarizer, audio_path: Path, *,
                             language: str | None, beam_size: int,
                             vad_filter: bool, num_speakers: int | None = None,
                             min_speakers: int | None = None,
                             max_speakers: int | None = None,
                             ) -> list[CaptionSegment]:
    """Transcreve com falante por palavra (``src/audio/file_pipeline.py``)."""
    from src.audio.file_pipeline import transcribe_audio_file

    result = transcribe_audio_file(
        audio_path, model=model, language=language, beam_size=beam_size,
        vad_filter=vad_filter, diarize=True, require_diarization=True,
        num_speakers=num_speakers, min_speakers=min_speakers,
        max_speakers=max_speakers, diarizer=diarizer,
    )
    for seg in result.segments:
        print(f"   [{_fmt(seg.start)}] {seg.speaker}: {seg.text}", flush=True)
    print(f"   👥 {len({s.speaker for s in result.segments if s.speaker})} falante(s)")
    return result.segments


def write_outputs(segments: list[CaptionSegment], audio_path: Path,
                  formats: set[str],
                  speaker_names: dict[str, str] | None = None) -> list[Path]:
    """Grava .txt/.srt/.vtt ao lado do áudio. Retorna os caminhos criados."""
    exporter = SubtitleExporter()
    base = audio_path.with_suffix("")
    written: list[Path] = []
    if "txt" in formats:
        txt = base.with_suffix(".txt")
        exporter.save_txt(segments, str(txt), speaker_names)
        written.append(txt)
    if "srt" in formats:
        srt = base.with_suffix(".srt")
        exporter.save_srt(segments, str(srt), speaker_names)
        written.append(srt)
    if "vtt" in formats:
        vtt = base.with_suffix(".vtt")
        exporter.save_vtt(segments, str(vtt), speaker_names)
        written.append(vtt)
    return written


def _fmt(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcreve áudio gravado e gera legendas .txt/.srt/.vtt",
    )
    parser.add_argument("paths", nargs="+",
                        help="Arquivo(s) de áudio ou diretório(s), ex.: data/recordings")
    parser.add_argument("--model", default=settings.stt_model,
                        help=f"Modelo Whisper (padrão: {settings.stt_model})")
    parser.add_argument("--language", default=settings.stt_language,
                        help=f"Idioma; 'auto' para detectar (padrão: {settings.stt_language})")
    parser.add_argument("--beam-size", type=int, default=settings.stt_beam_size,
                        help=f"Beam size (padrão: {settings.stt_beam_size})")
    parser.add_argument("--device", default=settings.stt_device,
                        choices=["auto", "cpu", "cuda"],
                        help=f"Dispositivo (padrão: {settings.stt_device})")
    parser.add_argument("--no-vad", action="store_true",
                        help="Desliga o filtro VAD (Silero)")
    parser.add_argument("--formats", default="txt,srt,vtt",
                        help="Formatos de saída separados por vírgula (padrão: txt,srt,vtt)")
    parser.add_argument("--force", action="store_true",
                        help="Reprocessa mesmo se o .srt já existir")
    parser.add_argument("--diarize", action="store_true",
                        help="Separa os falantes pela voz (requer .[diarization] + HF_TOKEN)")
    parser.add_argument("--num-speakers", type=int,
                        help="Nº de falantes, se souber (melhora a separação)")
    parser.add_argument("--min-speakers", type=int)
    parser.add_argument("--max-speakers", type=int)
    parser.add_argument("--speaker-map",
                        help="JSON com nomes: {\"SPEAKER_00\": \"Juliana\"}")
    args = parser.parse_args(argv)
    speaker_names = load_speaker_map(args.speaker_map)

    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    invalid = formats - {"txt", "srt", "vtt"}
    if invalid:
        parser.error(f"formato(s) inválido(s): {', '.join(sorted(invalid))}")

    files = collect_inputs(args.paths)
    if not args.force:
        pending = [f for f in files if not f.with_suffix(".srt").exists()]
        for f in sorted(set(files) - set(pending)):
            print(f"⏭️  Já tem legenda, pulando (use --force): {f}")
        files = pending
    if not files:
        print("Nenhum arquivo de áudio para transcrever.")
        return 0

    language = None if args.language == "auto" else args.language
    diarizer = None
    if args.diarize:
        from src.audio.offline_diarizer import DiarizationUnavailable, OfflineDiarizer
        diarizer = OfflineDiarizer()
        try:
            diarizer.check_ready()  # falha antes de carregar o Whisper
        except DiarizationUnavailable as e:
            print(f"❌ {e}", file=sys.stderr)
            return 2
    print(f"📥 Carregando modelo Whisper '{args.model}'...")
    try:
        model = load_model(args.model, args.device)
    except ImportError:
        print("❌ faster-whisper não instalado: pip install -e \".[audio]\"",
              file=sys.stderr)
        return 1

    failures = 0
    for audio_path in files:
        print(f"\n🎙️  Transcrevendo: {audio_path}")
        t0 = time.monotonic()
        try:
            if args.diarize:
                segments = transcribe_with_speakers(
                    model, diarizer, audio_path, language=language,
                    beam_size=args.beam_size, vad_filter=not args.no_vad,
                    num_speakers=args.num_speakers,
                    min_speakers=args.min_speakers,
                    max_speakers=args.max_speakers,
                )
            else:
                segments = transcribe(model, audio_path, language=language,
                                      beam_size=args.beam_size,
                                      vad_filter=not args.no_vad)
        except Exception as e:
            print(f"❌ Falha ao transcrever {audio_path}: {e}", file=sys.stderr)
            failures += 1
            continue
        if not segments:
            print("⚠️  Nenhuma fala detectada; nenhum arquivo gerado.")
            continue
        written = write_outputs(segments, audio_path, formats, speaker_names)
        print(f"✅ {len(segments)} segmentos em {time.monotonic() - t0:.1f}s:")
        for w in written:
            print(f"   {w}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
