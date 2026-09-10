"""GOLD-01..GOLD-02 — Golden master: verificação contra baseline congelada.

Classificação honesta: sintético/offline. Verifica que o corpus versionado
permanece íntegro contra a baseline congelada em
``tests/golden/manifest.yaml`` (medições ESTÁVEIS apenas — ver política).

O freeze deliberado (com ``--confirm-golden-regen``) e a recusa sem a
flag também são testados aqui como contrato.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.fidelity_golden as golden_mod  # noqa: E402

pytestmark = pytest.mark.golden


class TestGoldenVerify:
    def test_corpus_matches_frozen_baseline(self):
        """GOLD-01: verify aprova o corpus atual contra o golden."""
        ok, diffs, _ = golden_mod.verify()
        assert ok, (
            "GOLDEN DRIFT detectado — regressão de fixture/corpus:\n"
            + "\n".join(
                f"  [{d['scenario']}] {d['metric']}: "
                f"{d['expected']!r} != {d['measured']!r}"
                for d in diffs
            )
        )

    def test_verify_detects_tampered_measurement(self, tmp_path):
        """O verify FALHA quando a propriedade é violada (não tautológico).

        Golden adulterado (RMS +1 dB) deve produzir diff — garante que o
        mecanismo detecta drift real.
        """
        import yaml

        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        # Adultera o RMS de um cenário em +1 dB (viola tolerância 0.05)
        scen = next(iter(golden_data["scenarios"]))
        golden_data["scenarios"][scen]["rms_dbfs"] = (
            golden_data["scenarios"][scen]["rms_dbfs"] + 1.0
        )
        tampered = tmp_path / "golden.yaml"
        with open(tampered, "w", encoding="utf-8") as f:
            yaml.safe_dump(golden_data, f)

        ok, diffs, _ = golden_mod.verify(golden_path=tampered)
        assert not ok
        assert any(d["scenario"] == scen and d["metric"] == "rms_dbfs"
                   for d in diffs)

    def test_verify_detects_missing_scenario(self, tmp_path):
        """Fixture removido do corpus é detectado como drift."""
        import yaml

        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        scen = next(iter(golden_data["scenarios"]))
        del golden_data["scenarios"][scen]
        tampered = tmp_path / "golden.yaml"
        with open(tampered, "w", encoding="utf-8") as f:
            yaml.safe_dump(golden_data, f)

        ok, diffs, _ = golden_mod.verify(golden_path=tampered)
        assert not ok
        assert any(d["scenario"] == scen and d["metric"] == "presence"
                   for d in diffs)


class TestGoldenPolicy:
    def test_freeze_without_confirmation_is_refused(self, tmp_path):
        """GOLD-01 (guard): freeze SEM a flag é recusado com erro claro."""
        with pytest.raises(SystemExit, match="RECUSADO"):
            golden_mod.freeze(confirm=False,
                              golden_path=tmp_path / "golden.yaml")

    def test_freeze_with_confirmation_writes_manifest(self, tmp_path):
        """Freeze COM a flag regenera o manifesto (ação deliberada)."""
        out = tmp_path / "golden.yaml"
        golden_mod.freeze(confirm=True, golden_path=out)
        assert out.exists()
        import yaml

        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert data["schema"] == golden_mod.GOLDEN_SCHEMA
        assert len(data["scenarios"]) >= 10

    def test_golden_manifest_only_stable_measurements(self):
        """GOLD-02: golden NUNCA contém wall-clock/jitter/caminhos.

        Campos permitidos por cenário: medições físicas estáveis apenas.
        """
        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        allowed = {
            "sample_rate", "n_samples", "duration_s", "rms_dbfs",
            "spectral_peak_hz", "dc_offset", "clipped_fraction", "sha256",
        }
        forbidden_substrings = ("jitter", "wall", "latency", "timestamp_",
                                "elapsed", "path", "tmp")
        for scen, vals in golden_data["scenarios"].items():
            extra = set(vals) - allowed
            assert not extra, (
                f"golden de {scen} contém campos não estáveis: {extra}"
            )
            for key in vals:
                for bad in forbidden_substrings:
                    assert bad not in key.lower(), (
                        f"campo suspeito '{key}' no golden de {scen}"
                    )

    def test_golden_manifest_policy_declared(self):
        """Política e tolerâncias versionadas no próprio golden."""
        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        assert "policy" in golden_data
        assert "tolerances" in golden_data
        assert golden_data["tolerances"]["rms_dbfs"] == pytest.approx(0.05)
        assert golden_data["tolerances"]["sha256"] == "exact"

    def test_sine_1k_baseline_values(self):
        """Sanity: baseline do sine_1k guarda pico ~1 kHz e RMS ~-9 dBFS.

        Nota: senoide pura tem 1/8 das amostras exatamente no pico (dwell
        natural do seno no máximo — NÃO é clipping); o fixture `clipped`
        é o que carrega flat-topping real (fração de trilho elevada).
        """
        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        sine = golden_data["scenarios"]["sine_1k"]
        assert abs(sine["spectral_peak_hz"] - 1000.0) <= 0.5
        assert abs(sine["rms_dbfs"] - (-9.03)) <= 0.05
        # dwell natural do seno no pico: ~1/8 das amostras
        assert 0.10 <= sine["clipped_fraction"] <= 0.15

    def test_clipped_fixture_baseline_has_flat_topping(self):
        """Fixture deliberadamente clipado: fração de trilho ≥ 0.02 no
        golden (e muito acima do sinal limpo)."""
        golden_data = golden_mod._load_golden(golden_mod.GOLDEN_MANIFEST)
        clipped = golden_data["scenarios"]["clipped"]["clipped_fraction"]
        clean = golden_data["scenarios"]["clean_speech_like"][
            "clipped_fraction"
        ]
        assert clipped >= 0.02
        assert clean <= 0.001
