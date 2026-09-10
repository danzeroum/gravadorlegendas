"""Configuração global de testes: reset de structlog e outros estados globais."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import structlog
import yaml


def pytest_configure(config):
    """Executa antes de todos os testes: configura structlog com logger stdlib válido."""
    # Configurar logging stdlib primeiro
    logging.basicConfig(level=logging.DEBUG)

    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def pytest_unconfigure(config):
    """Executa após todos os testes."""
    structlog.reset_defaults()


# ---------------------------------------------------------------------------
# Fixtures do corpus de fidelidade (compartilhadas: fidelity/performance)
# ---------------------------------------------------------------------------

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "corpus"


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
