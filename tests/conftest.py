"""Configuração global de testes: reset de structlog e outros estados globais.

Também abriga a guarda de coleção da suíte de fidelidade: quando as deps
opcionais (extra ``[fidelity]``) estão ausentes — caso do job ``test`` do
CI, que instala apenas ``requirements.txt`` — os diretórios
fidelity/golden/contracts/performance saem da coleção em vez de falhar
com ImportError na coleta ou em runtime (imports lazy de scipy/jsonschema).
O dono desses testes é o job ``fidelity`` do CI (DECISOES.md D-014).
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
import structlog

# ---------------------------------------------------------------------------
# Guarda de coleção: deps opcionais da suíte de fidelidade (D-014)
# ---------------------------------------------------------------------------

_FIDELITY_DEPS = (
    "numpy", "scipy", "soundfile", "hypothesis", "jiwer",
    "yaml", "jsonschema",
)
_FIDELITY_DIRS = ("fidelity", "golden", "contracts", "performance")


def _missing_fidelity_deps() -> list:
    return [m for m in _FIDELITY_DEPS if importlib.util.find_spec(m) is None]


_MISSING_FIDELITY = _missing_fidelity_deps()

if _MISSING_FIDELITY:
    # Sem as deps opcionais a suíte NÃO entra na coleção (ausência
    # deliberada e anunciada — ver pytest_report_header abaixo), em vez
    # de falhar com ImportError. Validação red->green documentada em
    # DECISOES.md D-014.
    collect_ignore_glob = [f"{d}/test_*.py" for d in _FIDELITY_DIRS]


def pytest_report_header(config):
    if _MISSING_FIDELITY:
        return (
            "fidelity: deps opcionais ausentes (%s) — suítes "
            "fidelity/golden/contracts/performance fora da coleção nesta "
            "execução; dono delas é o job `fidelity` do CI "
            "(local: pip install -e .[fidelity])"
            % ", ".join(_MISSING_FIDELITY)
        )


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
    import yaml  # lazy: a coleção não deve exigir PyYAML direto (D-014)

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
