#!/usr/bin/env python3
"""Secret scanning direcionado em todos os arquivos alterados da branch.

Verifica padrões reais de segredo (GitHub PAT classic/fine-grained,
Hugging Face, OpenAI, chaves privadas, hex longo) em TODO o conteúdo
commitado da branch vs main. Nunca imprime o conteúdo dos arquivos —
apenas nomes e padrões detectados.

Além do conteúdo, verifica o **caminho** dos arquivos (Frente E0 do plano
de diarização, ``docs/diarizacao/PLANO-IMPLEMENTACAO.md``): áudio, RTTM e
voiceprints só podem existir no corpus sintético versionado. Gravações
reais, anotações reais e dados biométricos nunca entram no git (R3).

Uso:
    python scripts/secret_scan_changed_files.py            # conteúdo + caminho (vs main)
    python scripts/secret_scan_changed_files.py --tracked-paths
        # só caminho, sobre TODOS os arquivos versionados (usado no CI)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = {
    "github_pat_classic": re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    "github_pat_fine": re.compile(r"github_pat_[A-Za-z0-9_]{50,}"),
    "github_oauth": re.compile(r"gho_[A-Za-z0-9]{36,}"),
    "github_refresh": re.compile(r"ghr_[A-Za-z0-9]{76,}"),
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{40,}"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9\-_]{80,}"),
    "private_key_block": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    ),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_bearer": re.compile(
        r"(?i)(bearer|authorization)\s*[:=]\s*[A-Za-z0-9\-_\.]{40,}"
    ),
    "env_assignment_secret": re.compile(
        r"(?i)^(GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|"
        r"API_KEY|SECRET|PASSWORD)\s*=\s*[A-Za-z0-9\-_]{20,}$"
    ),
    "long_hex_secret": re.compile(r"\b[A-Fa-f0-9]{64,}\b"),
}


AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".flac", ".webm",
}
ALLOWED_AUDIO_DIR = "tests/fixtures/corpus/audio/"
ALLOWED_RTTM_DIR = "tests/fixtures/corpus/rttm/"


def classify_path(rel: str) -> str | None:
    """Regra de privacidade violada pelo caminho, ou None se permitido.

    Args:
        rel: Caminho relativo à raiz do repositório (separador ``/``).
    """
    rel = rel.replace("\\", "/")
    lower = rel.lower()
    if "voiceprint" in lower:
        return "voiceprint"
    suffix = Path(lower).suffix
    if suffix in AUDIO_EXTENSIONS and not rel.startswith(ALLOWED_AUDIO_DIR):
        return "audio_fora_do_corpus"
    if suffix == ".rttm" and not rel.startswith(ALLOWED_RTTM_DIR):
        return "rttm_fora_do_corpus"
    return None


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout
    return [f for f in out.splitlines() if f.strip()]


def scan_paths(paths: list[str]) -> int:
    """Imprime e conta caminhos que violam as regras de privacidade."""
    findings = 0
    for rel in paths:
        rule = classify_path(rel)
        if rule:
            findings += 1
            print(f"  BLOQUEADO: {rel} [regra: {rule}]")
    return findings


def changed_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT",
         "main...HEAD"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / f for f in out.splitlines() if f.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tracked-paths", action="store_true",
        help="Só checa caminhos, sobre todos os arquivos versionados.",
    )
    args = parser.parse_args(argv)

    if args.tracked_paths:
        paths = tracked_files()
        print(f"Checando caminho de {len(paths)} arquivo(s) versionados...")
        blocked = scan_paths(paths)
        if blocked:
            print(f"\n{blocked} arquivo(s) violam a regra de privacidade R3 "
                  "(áudio/RTTM/voiceprint fora do corpus sintético).")
            return 1
        print("Nenhum áudio, RTTM ou voiceprint fora do corpus sintético.")
        return 0

    files = changed_files()
    print(f"Analisando {len(files)} arquivo(s) alterados vs main...")
    findings = scan_paths([str(p.relative_to(ROOT)) for p in files])
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(path.relative_to(ROOT))
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(content):
                # ADJUDICAÇÃO (triage formal de secret scanning): os
                # manifests do corpus/golden contêm SHA-256 dos fixtures
                # sintéticos — hashes de integridade deliberados, não
                # segredos. Linha de allowlist com justificativa:
                if (
                    name == "long_hex_secret"
                    and rel in (
                        "tests/fixtures/corpus/manifest.yaml",
                        "tests/golden/manifest.yaml",
                    )
                    and "sha256" in content[max(0, match.start() - 80):
                                            match.start()].lower()
                ):
                    continue
                findings += 1
                # Imprime APENAS o nome do arquivo/padrão — nunca o match
                print(f"  SUSPEITO: {rel} [padrão: {name}]")
    if findings:
        print(f"\n{findings} ocorrência(s) suspeita(s) — revisar!")
        return 1
    print("\nNenhum padrão de segredo detectado nos arquivos alterados.")
    print("(SHA-256 de fixtures nos manifests = integridade deliberada, "
          "adjudicado como falso positivo.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
