"""REP-01..REP-02 — Contrato do relatório JSON de fidelidade.

Classificação honesta: sintético/offline. Valida que:
1. o schema versionado é um JSON Schema Draft-07 válido;
2. o gerador REAL (scripts/build_fidelity_report.py) produz relatórios
   conformes ao schema — inclusive em modo rápido (sem pytest);
3. relatórios inválidos são REJEITADOS (o teste falha quando a propriedade
   é violada — não tautológico);
4. skip tem motivo rastreável e limitações nunca são vazias (honestidade).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_fidelity_report as report_mod  # noqa: E402

pytestmark = pytest.mark.fidelity

SCHEMA_PATH = ROOT / "schemas" / "audio-fidelity-report-v1.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema):
    import jsonschema

    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


# ---------------------------------------------------------------------------
# REP-01 — Schema versionado válido e com as garantias de honestidade
# ---------------------------------------------------------------------------

class TestSchemaContract:
    def test_schema_is_valid_draft7(self, schema):
        import jsonschema

        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_version_const_is_1(self, schema):
        assert schema["properties"]["schema_version"]["const"] == "1"

    def test_schema_requires_core_fields(self, schema):
        required = set(schema["required"])
        assert {
            "schema_version", "generated_at", "environment", "summary",
            "results", "limitations",
        } <= required

    def test_schema_forbids_empty_limitations(self, schema):
        """Limitações nunca vazias — honestidade estrutural."""
        assert schema["properties"]["limitations"]["minItems"] == 1

    def test_schema_enforces_status_enum(self, schema):
        statuses = schema["properties"]["results"]["items"]["properties"][
            "status"
        ]["enum"]
        assert "skipped" in statuses
        assert "xfailed" in statuses
        assert "passed" in statuses

    def test_schema_enforces_category_enum(self, schema):
        categories = schema["properties"]["results"]["items"]["properties"][
            "category"
        ]["enum"]
        # As categorias honestas da suíte estão todas no contrato
        for expected in ("sintetico-offline", "integracao-real-lib",
                         "hardware-loopback", "requer-modelo-hf",
                         "requer-token-hf", "indisponivel-runner"):
            assert expected in categories

    def test_schema_file_has_no_secret_values(self):
        """O schema não contém VALORES de segredo (padrões reais de token),
        não a palavra 'token' em texto descritivo que declara a política."""
        import re

        content = SCHEMA_PATH.read_text(encoding="utf-8")
        secret_patterns = [
            r"ghp_[A-Za-z0-9]{20,}",       # GitHub PAT (classic)
            r"github_pat_[A-Za-z0-9_]{20,}",  # GitHub PAT (fine-grained)
            r"hf_[A-Za-z0-9]{20,}",        # Hugging Face token
            r"sk-[A-Za-z0-9]{20,}",        # API key genérica
            r"[A-Fa-f0-9]{40,}",           # hex longo (chave/secreto)
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        ]
        for pattern in secret_patterns:
            assert not re.search(pattern, content), (
                f"padrão de segredo {pattern!r} encontrado no schema"
            )


# ---------------------------------------------------------------------------
# REP-02 — O gerador REAL produz relatórios conformes
# ---------------------------------------------------------------------------

class TestReportBuilder:
    def test_build_report_no_pytest_validates(self, validator):
        """Gerador real em modo rápido: saída válida contra o schema."""
        report = report_mod.build_report(results=[])
        report_mod.validate_schema(report)
        assert report["schema_version"] == "1"
        assert report["summary"]["total"] == 0
        assert len(report["limitations"]) >= 1
        assert report["golden"]["status"] in (
            "verified", "drifted", "not-run"
        )

    def test_build_report_with_sample_results_validates(self, validator):
        """Resultados representativos (passed/skipped/xfailed) conformes."""
        results = [
            {
                "test_id": "tests/fidelity/test_x.py::T::test_a",
                "test_name": "T::test_a",
                "status": "passed",
                "category": "sintetico-offline",
                "metrics": {"snr_db": 10.0},
                "thresholds": {"snr_min_db": 3.0},
                "skip_reason": None,
                "duration_s": 0.01,
            },
            {
                "test_id": "tests/fidelity/test_y.py::T::test_b",
                "test_name": "T::test_b",
                "status": "skipped",
                "category": "requer-modelo-hf",
                "metrics": None,
                "thresholds": None,
                "skip_reason": "modelo não em cache",
                "duration_s": 0.0,
            },
            {
                "test_id": "tests/fidelity/test_z.py::T::test_c",
                "test_name": "T::test_c",
                "status": "xfailed",
                "category": "requer-modelo-hf",
                "metrics": None,
                "thresholds": None,
                "skip_reason": None,
                "duration_s": 0.02,
            },
        ]
        report = report_mod.build_report(results=results,
                                         golden={"status": "verified",
                                                 "n_scenarios": 10,
                                                 "diffs": []})
        report_mod.validate_schema(report)
        assert report["summary"]["total"] == 3
        assert report["summary"]["passed"] == 1
        assert report["summary"]["skipped"] == 1
        assert report["summary"]["xfailed"] == 1

    def test_environment_is_not_sensitive(self):
        """O ambiente reportado contém versões/booleanos — sem caminhos
        de usuário nem valores de variáveis de ambiente sensíveis."""
        env = report_mod._environment()
        blob = json.dumps(env).lower()
        assert str(Path.home()).lower() not in blob
        for forbidden in ("hf_token", "hugging_face_hub_token",
                          "github_token", "gh_token", "password", "secret"):
            assert forbidden not in blob, (
                f"campo sensível {forbidden!r} vazou no ambiente: {blob}"
            )

    def test_metrics_summary_offline_measurable(self):
        """Métricas offline mensuráveis presentes; as dependentes de
        modelo ficam null (declaradas), não omitidas."""
        metrics = report_mod._metrics_summary()
        assert "sine_spectral_peak_hz" in metrics
        assert metrics.get("wer") is None  # exige modelo — null declarado
        assert "snr_db" in metrics


# ---------------------------------------------------------------------------
# REP-02 (negativo) — relatórios inválidos são rejeitados
# ---------------------------------------------------------------------------

class TestSchemaRejectsInvalidReports:
    def _base_report(self) -> dict:
        return report_mod.build_report(results=[])

    def test_missing_required_field_rejected(self, validator):
        report = self._base_report()
        del report["summary"]
        with pytest.raises(Exception):
            validator.validate(report)

    def test_empty_limitations_rejected(self, validator):
        report = self._base_report()
        report["limitations"] = []
        with pytest.raises(Exception):
            validator.validate(report)

    def test_invalid_status_rejected(self, validator):
        report = self._base_report()
        report["results"] = [{
            "test_id": "x", "test_name": "x", "status": "green",
            "category": "sintetico-offline",
        }]
        with pytest.raises(Exception):
            validator.validate(report)

    def test_invalid_category_rejected(self, validator):
        report = self._base_report()
        report["results"] = [{
            "test_id": "x", "test_name": "x", "status": "passed",
            "category": "tudo-que-roda-e-real",
        }]
        with pytest.raises(Exception):
            validator.validate(report)

    def test_skipped_without_reason_rejected(self, validator):
        """skip sem motivo rastreável é rejeitado PELO SCHEMA (if-then)."""
        report = self._base_report()
        report["results"] = [{
            "test_id": "x", "test_name": "x", "status": "skipped",
            "category": "sintetico-offline", "skip_reason": None,
        }]
        with pytest.raises(Exception):
            validator.validate(report)

    def test_skipped_with_reason_accepted(self, validator):
        """skip COM motivo rastreável passa no contrato."""
        report = self._base_report()
        report["results"] = [{
            "test_id": "x", "test_name": "x", "status": "skipped",
            "category": "requer-modelo-hf",
            "skip_reason": "modelo não está em cache",
        }]
        validator.validate(report)  # não deve levantar
