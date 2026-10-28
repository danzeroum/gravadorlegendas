"""Transcreve um áudio pelo nome, separando os participantes — feito para agentes.

Ponto de entrada único para o opencode (ver ``AGENTS.md``) e para uso manual.
Solte o arquivo em ``audios/`` e peça "transcreva o áudio XPTO":

    python scripts/transcrever_audio.py XPTO
    python scripts/transcrever_audio.py XPTO --participantes 3 --modelo small
    python scripts/transcrever_audio.py --renomear XPTO A=Juliana B=Daniel
    python scripts/transcrever_audio.py --listar
    python scripts/transcrever_audio.py --verificar

Como o áudio é encontrado: caminho direto, ou nome (sem extensão, sem
diferença de maiúsculas/acentos) em ``audios/``, na raiz do projeto e em
``data/recordings``. Nome exato vence; senão, nome que contém o termo.

Saída em ``audios/transcricoes/<nome>``: ``.txt``, ``.srt``, ``.vtt``, ``.md``
(legível, com cabeçalho) e ``.json`` (dados para renomear sem retranscrever).
A última parte da saída é um bloco ``=== RESULTADO ===`` fácil de ler.

Códigos de saída: 0 ok · 2 ambiente incompleto · 3 nome ambíguo ·
4 áudio não encontrado · 5 arquivo ilegível · 6 transcrição não encontrada
para renomear.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.file_decode import SUPPORTED_EXTENSIONS  # noqa: E402

AUDIO_DIR = ROOT / "audios"
OUTPUT_DIR = AUDIO_DIR / "transcricoes"
SEARCH_DIRS = (AUDIO_DIR, ROOT, ROOT / "data" / "recordings")

EXIT_ENV, EXIT_AMBIGUOUS, EXIT_NOT_FOUND, EXIT_DECODE, EXIT_NO_TRANSCRIPT = 2, 3, 4, 5, 6


class UserError(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Encontrar o áudio
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in text if ch.isalnum())


def list_audio_files(dirs=None) -> list[Path]:
    seen, files = set(), []
    for d in (SEARCH_DIRS if dirs is None else dirs):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                key = f.resolve()
                if key not in seen:
                    seen.add(key)
                    files.append(f)
    return files


def find_audio(query: str, dirs=None) -> Path:
    """Resolve "XPTO" para um arquivo de áudio/vídeo.

    Raises:
        UserError: não encontrado (4) ou ambíguo (3), com a lista de opções.
    """
    direct = Path(query).expanduser()
    for candidate in (direct, ROOT / direct):
        if candidate.is_file():
            return candidate

    files = list_audio_files(dirs)
    q = _norm(Path(query).stem if Path(query).suffix.lower() in SUPPORTED_EXTENSIONS else query)
    if not q:
        raise UserError("Informe o nome do áudio.", EXIT_NOT_FOUND)
    exact = [f for f in files if _norm(f.stem) == q]
    matches = exact or [f for f in files if q in _norm(f.stem)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        available = "\n".join(f"  - {_rel(f)}" for f in files) or "  (nenhum áudio encontrado)"
        raise UserError(
            f"Não encontrei áudio com o nome '{query}'. Coloque o arquivo em "
            f"'{_rel(AUDIO_DIR)}/'. Áudios disponíveis:\n{available}",
            EXIT_NOT_FOUND,
        )
    options = "\n".join(f"  - {_rel(f)}" for f in matches)
    raise UserError(f"Mais de um áudio combina com '{query}'. Qual deles?\n{options}",
                    EXIT_AMBIGUOUS)


def _rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Ambiente
# ---------------------------------------------------------------------------

def environment_report() -> dict:
    from src.audio.offline_diarizer import default_model, find_hf_token, module_available
    from src.audio.transcribe import whisper_model_dir
    from src.config import settings

    has = {m: module_available(m) for m in ("faster_whisper", "av", "pyannote.audio")}
    return {
        "python": sys.version.split()[0],
        "faster_whisper": has["faster_whisper"],
        "av": has["av"],
        "pyannote": has["pyannote.audio"],
        "hf_token": bool(find_hf_token()) if has["pyannote.audio"] else False,
        "diarization_model": settings.diarization_model or default_model(),
        "whisper_model": settings.stt_model,
        "whisper_cached": whisper_model_dir(settings.stt_model).is_dir(),
    }


def print_environment(rep: dict) -> int:
    ok = "✅"
    bad = "❌"
    print(f"Python {rep['python']}")
    print(f"{ok if rep['faster_whisper'] else bad} transcrição (faster-whisper)")
    print(f"{ok if rep['av'] else bad} leitura de mp3/m4a/mp4/ogg (PyAV)")
    cached = "já baixado" if rep["whisper_cached"] else "será baixado no primeiro uso"
    print(f"   modelo Whisper padrão: {rep['whisper_model']} ({cached})")
    print(f"{ok if rep['pyannote'] else bad} separação de participantes (pyannote.audio)")
    print(f"{ok if rep['hf_token'] else bad} token Hugging Face (HF_TOKEN ou huggingface-cli login)")
    print(f"   modelo de separação: {rep['diarization_model']}")
    steps = []
    if not (rep["faster_whisper"] and rep["av"]):
        steps.append("bash scripts/setup_ambiente.sh")
    if not rep["pyannote"]:
        steps.append("bash scripts/setup_ambiente.sh --separar-participantes")
    if rep["pyannote"] and not rep["hf_token"]:
        steps.append("definir HF_TOKEN no .env (ou 'huggingface-cli login') e aceitar os "
                     f"termos em https://hf.co/{rep['diarization_model']}")
    if steps:
        print("\nPara completar:")
        for s in steps:
            print(f"  - {s}")
    else:
        print("\nTudo pronto: transcrição e separação de participantes.")
    return 0 if rep["faster_whisper"] and rep["av"] else EXIT_ENV


# ---------------------------------------------------------------------------
# Nomes
# ---------------------------------------------------------------------------

def parse_names(pairs: list[str], speakers: dict[str, str]) -> dict[str, str]:
    """``["A=Juliana", "Participante B=Daniel", "SPEAKER_02=Ana"]`` → {sid: nome}."""
    names: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise UserError(f"Use o formato A=Nome (recebi '{pair}').", EXIT_NO_TRANSCRIPT)
        key, name = (p.strip() for p in pair.split("=", 1))
        k = _norm(key)
        sid = next(
            (sid for sid, label in speakers.items()
             if k in (_norm(sid), _norm(label), _norm(label.split()[-1]))),
            None,
        )
        if sid is None or not name:
            known = ", ".join(speakers.values()) or "nenhum"
            raise UserError(f"Participante '{key}' não existe nesta transcrição "
                            f"(participantes: {known}).", EXIT_NO_TRANSCRIPT)
        names[sid] = name
    return names


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def _clock(seconds: float) -> str:
    from src.storage.subtitle_exporter import format_clock
    return format_clock(seconds)


def to_markdown(data: dict) -> str:
    names = {**data["speakers"], **data.get("names", {})}
    lines = [f"# Transcrição — {data['arquivo']}", ""]
    lines.append(f"- **Duração:** {_clock(data['duration_s'])}")
    if data["diarized"]:
        lines.append(f"- **Participantes:** {', '.join(names[s] for s in data['speakers'])}")
    else:
        lines.append("- **Participantes:** não separados"
                     + (f" ({data['diarization_error']})" if data.get("diarization_error") else ""))
    lines.append(f"- **Modelo:** {data['modelo']}  ·  **Gerado em:** {data['gerado_em']}")
    lines += ["", "---", ""]
    for s in data["segments"]:
        who = names.get(s["speaker"], s["speaker"]) if s.get("speaker") else None
        prefix = f"**{who}** " if who else ""
        lines.append(f"{prefix}`[{_clock(s['start'])}]` {s['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_all(data: dict, base: Path) -> list[Path]:
    from src.audio.file_pipeline import transcript_from_dict, write_transcript_files

    transcript = transcript_from_dict(data)
    written = write_transcript_files(transcript, base, data.get("names") or {})
    md = base.with_suffix(".md")
    md.write_text(to_markdown(data), encoding="utf-8")
    js = base.with_suffix(".json")
    js.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written + [md, js]


def print_result(data: dict, files: list[Path], *, reused: bool = False) -> None:
    names = {**data["speakers"], **data.get("names", {})}
    print("\n=== RESULTADO ===")
    print(f"arquivo: {data['arquivo']}")
    print(f"duracao: {_clock(data['duration_s'])}")
    if data["diarized"]:
        parts = ", ".join(names[s] for s in data["speakers"])
        print(f"participantes: {len(data['speakers'])} ({parts})")
    else:
        print(f"participantes: não separados — {data.get('diarization_error') or 'desligado'}")
    print(f"trechos: {len(data['segments'])}")
    if reused:
        print("observacao: transcrição já existia (use --forcar para refazer)")
    for f in files:
        print(f"{f.suffix[1:]}: {_rel(f)}")


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_transcribe(args) -> int:
    rep = environment_report()
    if not (rep["faster_whisper"] and rep["av"]):
        print("❌ Transcrição indisponível: faltam dependências.", file=sys.stderr)
        print("   Rode: bash scripts/setup_ambiente.sh", file=sys.stderr)
        return EXIT_ENV

    audio = find_audio(args.audio)
    out_dir = Path(args.saida) if args.saida else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / audio.stem
    sidecar = base.with_suffix(".json")
    if sidecar.exists() and not args.forcar and not args.nomes:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        files = [base.with_suffix(e) for e in (".txt", ".srt", ".vtt", ".md", ".json")]
        print_result(data, [f for f in files if f.exists()], reused=True)
        return 0

    from src.audio.file_decode import AudioDecodeError
    from src.audio.file_pipeline import transcribe_audio_file
    from src.config import settings

    model = args.modelo or settings.stt_model
    print(f"🎙️  Transcrevendo {_rel(audio)} (modelo {model})…", flush=True)
    last = [-1]

    def progress(fraction: float, stage: str) -> None:
        pct = int(fraction * 100) // 10 * 10
        if pct != last[0]:
            last[0] = pct
            print(f"   {pct:3d}% {stage}", flush=True)

    t0 = time.monotonic()
    try:
        result = transcribe_audio_file(
            audio, model_size=model, diarize=not args.sem_separar,
            num_speakers=args.participantes, on_progress=progress,
        )
    except AudioDecodeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return EXIT_DECODE
    if not result.diarized and result.diarization_error and not args.sem_separar:
        print(f"⚠️  Participantes não separados: {result.diarization_error}", flush=True)

    data = {
        "arquivo": _rel(audio),
        "modelo": model,
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "segundos_processamento": round(time.monotonic() - t0, 1),
        **_transcript_dict(result),
        "names": {},
    }
    if args.nomes:
        data["names"] = parse_names(args.nomes, data["speakers"])
    if not data["segments"]:
        print("⚠️  Nenhuma fala detectada no áudio.")
    print_result(data, write_all(data, base))
    return 0


def _transcript_dict(result) -> dict:
    from src.audio.file_pipeline import transcript_to_dict
    d = transcript_to_dict(result)
    d["source"] = _rel(Path(d["source"]))  # sem caminho absoluto da máquina
    return d


def cmd_rename(args) -> int:
    query, pairs = args.renomear[0], args.renomear[1:]
    out_dir = Path(args.saida) if args.saida else OUTPUT_DIR
    candidates = sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []
    q = _norm(Path(query).stem)
    exact = [c for c in candidates if _norm(c.stem) == q]
    matches = exact or [c for c in candidates if q in _norm(c.stem)]
    if len(matches) != 1:
        opts = "\n".join(f"  - {c.stem}" for c in (matches or candidates)) or "  (nenhuma)"
        raise UserError(
            f"{'Mais de uma' if matches else 'Nenhuma'} transcrição para '{query}'. "
            f"Transcrições disponíveis:\n{opts}",
            EXIT_AMBIGUOUS if matches else EXIT_NO_TRANSCRIPT,
        )
    sidecar = matches[0]
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    if not data["diarized"]:
        raise UserError("Esta transcrição não separou participantes; não há quem renomear.",
                        EXIT_NO_TRANSCRIPT)
    if not pairs:
        raise UserError("Informe os nomes, ex.: A=Juliana B=Daniel", EXIT_NO_TRANSCRIPT)
    data["names"] = {**data.get("names", {}), **parse_names(pairs, data["speakers"])}
    print_result(data, write_all(data, sidecar.with_suffix("")))
    return 0


def cmd_list() -> int:
    files = list_audio_files()
    if not files:
        print(f"Nenhum áudio encontrado. Coloque arquivos em '{_rel(AUDIO_DIR)}/'.")
        return 0
    print("Áudios disponíveis:")
    for f in files:
        done = (OUTPUT_DIR / f.stem).with_suffix(".json").exists()
        print(f"  - {_rel(f)}{'  (já transcrito)' if done else ''}")
    return 0


def _quiet_logs() -> None:
    """Só avisos e erros dos módulos internos: a saída é lida por um agente."""
    import logging

    import structlog
    logging.getLogger().setLevel(logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcreve um áudio pelo nome, separando os participantes.")
    parser.add_argument("audio", nargs="?", help="nome ou caminho do áudio (ex.: XPTO)")
    parser.add_argument("--participantes", type=int,
                        help="quantas pessoas falam, se souber (melhora a separação)")
    parser.add_argument("--modelo", help="modelo Whisper: tiny, base, small, medium, large-v3")
    parser.add_argument("--sem-separar", action="store_true",
                        help="só transcreve, sem separar participantes")
    parser.add_argument("--nomes", nargs="+", metavar="A=Nome",
                        help="nomes dos participantes, ex.: A=Juliana B=Daniel")
    parser.add_argument("--forcar", action="store_true", help="refaz mesmo se já transcrito")
    parser.add_argument("--saida", help=f"pasta de saída (padrão: {_rel(OUTPUT_DIR)})")
    parser.add_argument("--renomear", nargs="+", metavar="ARG",
                        help="NOME A=Juliana B=Daniel — renomeia sem retranscrever")
    parser.add_argument("--listar", action="store_true", help="lista os áudios disponíveis")
    parser.add_argument("--verificar", action="store_true", help="checa o ambiente")
    args = parser.parse_args(argv)
    _quiet_logs()

    try:
        if args.verificar:
            return print_environment(environment_report())
        if args.listar:
            return cmd_list()
        if args.renomear:
            return cmd_rename(args)
        if not args.audio:
            parser.error("informe o nome do áudio (ou --listar / --verificar)")
        return cmd_transcribe(args)
    except UserError as e:
        print(f"❌ {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
