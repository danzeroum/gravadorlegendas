#!/usr/bin/env python3
"""Secret scanning direcionado em todos os arquivos alterados da branch.

Verifica padrões reais de segredo (GitHub PAT classic/fine-grained,
Hugging Face, OpenAI, chaves privadas, hex longo) em TODO o conteúdo
commitado da branch vs main. Nunca imprime o conteúdo dos arquivos —
apenas nomes e padrões detectados.
"""
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


def changed_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT",
         "main...HEAD"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / f for f in out.splitlines() if f.strip()]


def main() -> int:
    files = changed_files()
    print(f"Analisando {len(files)} arquivo(s) alterados vs main...")
    findings = 0
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
