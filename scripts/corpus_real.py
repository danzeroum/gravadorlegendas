"""Corpus real de avaliação de diarização — fora do repositório (Frente H1).

Gerencia um conjunto local de reuniões reais anotadas (áudio + RTTM +
transcrição opcional) para medir DER/cpWER do pipeline em vozes humanas.
O corpus sintético versionado (``tests/fixtures/corpus``) continua sendo o
único usado no CI.

Regras (``docs/diarizacao/PLANO-IMPLEMENTACAO.md``, R3 e D-021):
- o diretório do corpus **nunca** pode ficar dentro do repositório;
- cada item registra sha256, referência de consentimento e prazo de retenção;
- ``verify`` falha se algo disso estiver ausente, alterado ou vencido;
- cifragem é responsabilidade do volume (LUKS/BitLocker), não do app.

Uso:
    python scripts/corpus_real.py init --dir ~/corpus_real --name golden-2026-q4
    python scripts/corpus_real.py add --dir ~/corpus_real --audio reuniao.m4a \\
        --rttm reuniao.rttm --consent-ref TERMO-2026-017 --retain-until 2027-04-01
    python scripts/corpus_real.py import-labels --audacity labels.txt --out reuniao.rttm
    python scripts/corpus_real.py verify --dir ~/corpus_real
    python scripts/corpus_real.py purge --dir ~/corpus_real --dry-run

Formato da transcrição opcional (``--transcript``): uma fala por linha,
``FALANTE<TAB>texto``, com os mesmos rótulos do RTTM. É o que permite cpWER.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "gravadorlegendas/corpus-real@1"
MANIFEST = "manifest.yaml"


class CorpusError(Exception):
    """Erro acionável do corpus real (mensagem vai para o usuário)."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _yaml():
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - dep do extra fidelity
        raise CorpusError("PyYAML ausente: pip install -e \".[fidelity]\"") from e
    return yaml


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_outside_repo(path: Path, repo_root: Path = ROOT) -> Path:
    """Recusa diretório dentro do repositório (regra R3)."""
    resolved = path.expanduser().resolve()
    root = repo_root.resolve()
    if resolved == root or root in resolved.parents:
        raise CorpusError(
            f"O corpus real não pode ficar dentro do repositório ({root}). "
            "Use um diretório fora dele, de preferência em volume cifrado."
        )
    return resolved


def load_manifest(corpus_dir: Path) -> dict:
    path = corpus_dir / MANIFEST
    if not path.is_file():
        raise CorpusError(f"Manifest não encontrado: {path} (rode 'init').")
    data = _yaml().safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schema") != SCHEMA:
        raise CorpusError(f"Schema inesperado em {path}: {data.get('schema')!r}")
    data.setdefault("items", [])
    return data


def save_manifest(corpus_dir: Path, data: dict) -> None:
    (corpus_dir / MANIFEST).write_text(
        _yaml().safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise CorpusError(f"{field} inválido (use AAAA-MM-DD): {value!r}") from e


# ---------------------------------------------------------------------------
# Labels (Audacity / ELAN tab-delimited) -> RTTM
# ---------------------------------------------------------------------------

def labels_to_rttm(labels_text: str, uri: str) -> str:
    """Converte labels ``inicio<TAB>fim<TAB>FALANTE`` em texto RTTM.

    Aceita o export de faixa de rótulos do Audacity e o "tab-delimited
    text" do ELAN (colunas de tempo em segundos). Linhas de frequência do
    Audacity (começando com ``\\``) e vazias são ignoradas.
    """
    from src.audio.rttm import format_rttm

    segments = []
    for n, raw in enumerate(labels_text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("\\"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            raise CorpusError(f"linha {n}: esperado 'inicio<TAB>fim<TAB>FALANTE'")
        try:
            start, end = float(parts[0]), float(parts[1])
        except ValueError as e:
            raise CorpusError(f"linha {n}: tempos inválidos") from e
        speaker = parts[2].strip().replace(" ", "_")
        if end <= start or not speaker:
            raise CorpusError(f"linha {n}: intervalo vazio ou falante ausente")
        segments.append({"speaker": speaker, "start": start, "end": end})
    return format_rttm(segments, uri)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_init(corpus_dir: Path, name: str) -> Path:
    corpus_dir = ensure_outside_repo(corpus_dir)
    if (corpus_dir / MANIFEST).exists():
        raise CorpusError(f"Já existe um corpus em {corpus_dir}.")
    for sub in ("audio", "rttm", "transcripts"):
        (corpus_dir / sub).mkdir(parents=True, exist_ok=True)
    save_manifest(corpus_dir, {
        "schema": SCHEMA,
        "name": name,
        "contains_personal_audio": True,
        "storage_note": ("diretório em volume cifrado (LUKS/BitLocker) — "
                         "responsabilidade do operador"),
        "sample_rate": 16000,
        "channels": 1,
        "items": [],
    })
    return corpus_dir


def cmd_add(corpus_dir: Path, audio: Path, rttm: Path, consent_ref: str,
            retain_until: str, transcript: Path | None = None,
            item_id: str | None = None,
            num_speakers: int | None = None) -> dict:
    from src.audio.file_decode import decode_to_wav16k

    corpus_dir = ensure_outside_repo(corpus_dir)
    data = load_manifest(corpus_dir)
    if not consent_ref.strip():
        raise CorpusError("--consent-ref é obrigatório (referência do termo).")
    _parse_date(retain_until, "--retain-until")
    item_id = item_id or audio.stem
    if any(i["id"] == item_id for i in data["items"]):
        raise CorpusError(f"Item '{item_id}' já existe no corpus.")

    from src.audio.rttm import parse_rttm
    ref_segments = parse_rttm(rttm)
    if not ref_segments:
        raise CorpusError(f"RTTM sem segmentos SPEAKER: {rttm}")

    audio_out = corpus_dir / "audio" / f"{item_id}.wav"
    rttm_out = corpus_dir / "rttm" / f"{item_id}.rttm"
    decode_to_wav16k(audio, audio_out)
    shutil.copyfile(rttm, rttm_out)
    item = {
        "id": item_id,
        "audio": f"audio/{audio_out.name}",
        "rttm": f"rttm/{rttm_out.name}",
        "sha256": {"audio": sha256_file(audio_out),
                   "rttm": sha256_file(rttm_out)},
        "num_speakers": num_speakers or len({s["speaker"] for s in ref_segments}),
        "consent_ref": consent_ref,
        "retain_until": str(retain_until),
    }
    if transcript is not None:
        tr_out = corpus_dir / "transcripts" / f"{item_id}.txt"
        shutil.copyfile(transcript, tr_out)
        item["transcript"] = f"transcripts/{tr_out.name}"
        item["sha256"]["transcript"] = sha256_file(tr_out)
    data["items"].append(item)
    save_manifest(corpus_dir, data)
    return item


def cmd_verify(corpus_dir: Path, today: date | None = None) -> list[str]:
    """Lista de problemas (vazia = corpus íntegro)."""
    today = today or date.today()
    problems: list[str] = []
    try:
        corpus_dir = ensure_outside_repo(corpus_dir)
        data = load_manifest(corpus_dir)
    except CorpusError as e:
        return [str(e)]
    if data.get("contains_personal_audio") is not True:
        problems.append("manifest sem 'contains_personal_audio: true'")
    for item in data["items"]:
        iid = item.get("id", "?")
        if not str(item.get("consent_ref") or "").strip():
            problems.append(f"{iid}: sem referência de consentimento")
        try:
            if _parse_date(item.get("retain_until"), "retain_until") < today:
                problems.append(f"{iid}: retenção vencida em "
                                f"{item['retain_until']} (rode 'purge')")
        except CorpusError as e:
            problems.append(f"{iid}: {e}")
        for kind, expected in (item.get("sha256") or {}).items():
            path = corpus_dir / item.get(kind, "")
            if not path.is_file():
                problems.append(f"{iid}: arquivo ausente ({kind})")
            elif sha256_file(path) != expected:
                problems.append(f"{iid}: sha256 divergente ({kind})")
    return problems


def cmd_purge(corpus_dir: Path, dry_run: bool = False,
              today: date | None = None) -> list[str]:
    """Remove itens com retenção vencida. Retorna os IDs removidos."""
    today = today or date.today()
    corpus_dir = ensure_outside_repo(corpus_dir)
    data = load_manifest(corpus_dir)
    keep, removed = [], []
    for item in data["items"]:
        if _parse_date(item["retain_until"], "retain_until") < today:
            removed.append(item["id"])
            if not dry_run:
                for kind in ("audio", "rttm", "transcript"):
                    if item.get(kind):
                        (corpus_dir / item[kind]).unlink(missing_ok=True)
        else:
            keep.append(item)
    if removed and not dry_run:
        data["items"] = keep
        save_manifest(corpus_dir, data)
    return removed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="cria um corpus vazio")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("add", help="adiciona uma reunião anotada")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--audio", type=Path, required=True)
    p.add_argument("--rttm", type=Path, required=True)
    p.add_argument("--transcript", type=Path)
    p.add_argument("--id")
    p.add_argument("--num-speakers", type=int)
    p.add_argument("--consent-ref", required=True)
    p.add_argument("--retain-until", required=True)

    p = sub.add_parser("import-labels", help="labels Audacity/ELAN -> RTTM")
    p.add_argument("--audacity", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--uri")

    p = sub.add_parser("verify", help="confere hashes, consentimento e prazos")
    p.add_argument("--dir", type=Path, required=True)

    p = sub.add_parser("purge", help="remove itens com retenção vencida")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            print(f"Corpus criado em {cmd_init(args.dir, args.name)}")
        elif args.cmd == "add":
            item = cmd_add(args.dir, args.audio, args.rttm, args.consent_ref,
                           args.retain_until, args.transcript, args.id,
                           args.num_speakers)
            print(f"Item '{item['id']}' adicionado "
                  f"({item['num_speakers']} falantes).")
        elif args.cmd == "import-labels":
            uri = args.uri or args.out.stem
            args.out.write_text(
                labels_to_rttm(args.audacity.read_text(encoding="utf-8"), uri),
                encoding="utf-8",
            )
            print(f"RTTM gravado em {args.out}")
        elif args.cmd == "verify":
            problems = cmd_verify(args.dir)
            for msg in problems:
                print(f"  PROBLEMA: {msg}")
            if problems:
                return 1
            print("Corpus íntegro: hashes, consentimento e prazos OK.")
        elif args.cmd == "purge":
            removed = cmd_purge(args.dir, dry_run=args.dry_run)
            verb = "Seriam removidos" if args.dry_run else "Removidos"
            print(f"{verb}: {', '.join(removed) if removed else 'nenhum item'}")
    except CorpusError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
