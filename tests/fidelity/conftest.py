"""Fixtures compartilhadas dos testes de fidelidade de áudio."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

FIDELITY_DIR = Path(__file__).resolve().parent
TESTS_DIR = FIDELITY_DIR.parent
CORPUS_DIR = TESTS_DIR / "fixtures" / "corpus"


@pytest.fixture(scope="session")
def corpus_manifest() -> dict:
    """Manifesto do corpus determinístico (tests/fixtures/corpus/manifest.yaml)."""
    manifest_path = CORPUS_DIR / "manifest.yaml"
    if not manifest_path.exists():
        pytest.fail(
            "manifest.yaml do corpus não existe — rode "
            "`python scripts/gen_fidelity_fixtures.py`"
        )
    with open(manifest_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def corpus_scenario(corpus_manifest):
    """Índice de cenários do corpus por id."""
    return {s["id"]: s for s in corpus_manifest["scenarios"]}


@pytest.fixture(scope="session")
def corpus_audio_dir() -> Path:
    return CORPUS_DIR / "audio"
