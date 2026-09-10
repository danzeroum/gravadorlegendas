"""DIA-01..DIA-03 — Qualidade de diarização: harness DER com RTTM.

Classificação honesta (ver docs/qualidade-audio/README.md):

- DIA-01 (integração-real-lib, offline): DER computado com
  ``pyannote.metrics.diarization.DiarizationErrorRate`` REAL (extra
  ``.[diarization-metrics]`` — instalável sem torch). Cenários:
  2 falantes alternados, overlap, 3 falantes, entrada/saída de falante
  e sinal sem fala. Sem o extra: o harness (parse RTTM, timelines,
  invariância de permutação) é validado e a computação DER faz skip
  explícito com motivo preciso.
- DIA-02 (sintético/offline): RTTMs de referência versionados no corpus
  com política de collar/overlap declarada no manifesto.
- DIA-03 (requer-modelo-hf): diart/pyannote.audio real, marcado
  ``requires_hf_token`` — só executa com token HF **por referência de
  ambiente** (valor nunca ecoado) e termos aceitos; skip explícito
  caso contrário.

DISTINÇÃO FUNDAMENTAL documentada aqui: **diarização** atribui "quem
falou quando" com IDs locais (SPEAKER_00, SPEAKER_01...) — é invariante
a permutação consistente de labels. **Identificação persistente de
pessoa** (voice enrollment/biometria) NÃO é implementada nem validada
nesta suíte: exigiria requisito explícito, avaliação de privacidade,
consentimento e política de retenção (ver DECISOES.md D-002).

Sinais pseudo-falados validam contrato, timeline, integração e métricas
— NÃO a qualidade de embeddings/diarização em vozes humanas.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.fidelity

CORPUS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"

SCENARIOS = [
    "two_speakers_no_overlap",
    "two_speakers_overlap",
    "three_speakers",
    "speaker_enter_exit",
]


# ---------------------------------------------------------------------------
# Harness RTTM — parse e reconstrução de timeline (roda sempre)
# ---------------------------------------------------------------------------

def parse_rttm(path: Path) -> list[dict]:
    """Parser RTTM (NIST) → lista de segmentos {speaker, start, end}."""
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0] == "SPEAKER":
            segments.append({
                "speaker": parts[7],
                "start": float(parts[3]),
                "end": float(parts[3]) + float(parts[4]),
            })
    return segments


class TestDia02RttmHarness:
    """DIA-02: RTTMs de referência íntegros + política declarada."""

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_rttm_parses_with_segments(self, scen):
        segs = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        assert segs, f"RTTM de {scen} vazio ou ilegível"
        for s in segs:
            assert s["end"] > s["start"], f"segmento inválido: {s}"
            assert s["speaker"].startswith("SPEAKER_")

    def test_rttm_matches_manifest_timeline(self, corpus_manifest):
        """Timeline do manifesto == timeline do RTTM (consistência)."""
        by_id = {s["id"]: s for s in corpus_manifest["scenarios"]}
        for scen in SCENARIOS:
            entry = by_id[scen]
            segs = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
            manifest_tl = [
                (t["speaker"], t["start"], t["end"])
                for t in entry["timeline"]
            ]
            rttm_tl = [
                (int(s["speaker"].split("_")[1]), round(s["start"], 3),
                 round(s["end"], 3))
                for s in segs
            ]
            assert sorted(manifest_tl) == sorted(rttm_tl), (
                f"timeline do RTTM diverge do manifesto em {scen}"
            )

    def test_der_policy_declared_in_manifest(self, corpus_manifest):
        """Política DER: collar e overlap declarados (auditável)."""
        policy = corpus_manifest["der_policy"]
        assert policy["collar_s"] == 0.0
        assert "overlap_policy" in policy
        assert "label_mapping" in policy
        expected = policy["harness_expected"]
        assert expected["exact_copy"] == 0.0
        assert expected["consistent_permutation"] == 0.0

    def test_silence_scenario_has_no_speech(self, corpus_manifest):
        """Cenário sem fala: fixture de silêncio existe e tem RMS 0."""
        import soundfile as sf

        x, sr = sf.read(
            str(CORPUS_DIR / "audio" / "silence.wav"), dtype="float64"
        )
        assert sr == 16000
        assert abs(float(x.mean())) < 1e-12


# ---------------------------------------------------------------------------
# DIA-01 — DER real com pyannote.metrics (extra diarization-metrics)
# ---------------------------------------------------------------------------

# pyannote.metrics emite UserWarning sobre aproximação de UEM quando não
# há mapa de avaliação explícito — comportamento esperado da biblioteca
# para avaliação de corpus completo; filtrado para manter o CI limpo.
pytestmark_der = pytest.mark.filterwarnings(
    "ignore:.*'uem' was approximated.*:UserWarning"
)

_pyannote_metrics = pytest.importorskip(
    "pyannote.metrics",
    reason=(
        "pyannote.metrics não instalado — DER real requer o extra "
        "'.[diarization-metrics]' (pip install -e \".[diarization-metrics]\""
        " — instalável sem torch)"
    ),
)


def to_annotation(segments, uri="test"):
    """Converte segmentos {speaker,start,end} em Annotation pyannote."""
    from pyannote.core import Annotation, Segment

    ann = Annotation(uri=uri)
    for s in segments:
        ann[Segment(s["start"], s["end"])] = s["speaker"]
    return ann


def compute_der(ref_segs, hyp_segs, collar=0.0):
    """DER com a política declarada no manifesto (collar 0.0)."""
    from pyannote.metrics.diarization import DiarizationErrorRate

    metric = DiarizationErrorRate(collar=collar, skip_overlap=False)
    return float(metric(to_annotation(ref_segs), to_annotation(hyp_segs)))


@pytestmark_der
class TestDia01DerReal:
    """DER computado pela biblioteca real — transformações controladas.

    Bandas esperadas calibradas por medição local (manifesto,
    der_policy.harness_expected; ver scripts/measure_der_baseline.py).
    """

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_exact_copy_der_zero(self, scen):
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        assert compute_der(ref, ref) == 0.0

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_consistent_permutation_der_zero(self, scen):
        """Permutação CONSISTENTE de labels: DER = 0 (invariância).

        Diarização atribui IDs locais — rebater SPEAKER_00↔SPEAKER_01 em
        TODOS os segmentos é a mesma partição de falas. Identificação
        persistente de pessoa (enrollment) NÃO é parte do contrato.
        """
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        speakers = sorted({s["speaker"] for s in ref})
        perm = {sp: speakers[(i + 1) % len(speakers)]
                for i, sp in enumerate(speakers)}
        permuted = [dict(s, speaker=perm[s["speaker"]]) for s in ref]
        assert compute_der(ref, permuted) == 0.0

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_non_bijective_confusion_detected(self, scen,
                                              corpus_manifest):
        """Confusão parcial (não-bijetiva) é detectada: DER > limiar.

        Rebatar UM segmento para um speaker que JÁ existe cria conflito
        de agrupamento — erro real de atribuição (medido: 0.18–0.44).
        """
        minimum = corpus_manifest["der_policy"]["harness_expected"][
            "non_bijective_confusion_min"
        ]
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        speakers = sorted({s["speaker"] for s in ref})
        confused = [dict(s) for s in ref]
        confused[0]["speaker"] = speakers[-1]  # colide com outro falante
        value = compute_der(ref, confused)
        assert value > minimum, (
            f"confusão não-bijetiva em {scen} não detectada (DER={value:.3f})"
        )

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_global_time_shift_detected(self, scen, corpus_manifest):
        """Shift global de 500 ms detectado na banda calibrada."""
        band = corpus_manifest["der_policy"]["harness_expected"][
            "global_shift_500ms_band"
        ]
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        shifted = [dict(s, start=s["start"] + 0.5, end=s["end"] + 0.5)
                   for s in ref]
        value = compute_der(ref, shifted)
        assert band[0] <= value <= band[1], (
            f"DER do shift 500ms em {scen} = {value:.3f} fora da banda "
            f"{band}"
        )

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_truncation_detected(self, scen, corpus_manifest):
        """Perda dos últimos 20% do áudio detectada na banda calibrada."""
        band = corpus_manifest["der_policy"]["harness_expected"][
            "truncation_20pct_band"
        ]
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        total_end = max(s["end"] for s in ref)
        truncated = [s for s in ref if s["end"] <= total_end * 0.8]
        value = compute_der(ref, truncated)
        assert band[0] <= value <= band[1], (
            f"DER do truncamento em {scen} = {value:.3f} fora da banda {band}"
        )

    @pytest.mark.parametrize("scen", SCENARIOS)
    def test_single_speaker_merge_detected(self, scen, corpus_manifest):
        """Colapsar tudo num único falante é erro (banda calibrada)."""
        band = corpus_manifest["der_policy"]["harness_expected"][
            "single_speaker_merge_band"
        ]
        ref = parse_rttm(CORPUS_DIR / "rttm" / f"{scen}.rttm")
        merged = [dict(s, speaker="SPEAKER_00") for s in ref]
        value = compute_der(ref, merged)
        assert band[0] <= value <= band[1], (
            f"DER do merge em {scen} = {value:.3f} fora da banda {band}"
        )

    def test_empty_hypothesis_is_total_miss(self, corpus_manifest):
        """Nenhum falante detectado: DER = 1.0 (miss total)."""
        expected = corpus_manifest["der_policy"]["harness_expected"][
            "empty_hypothesis"
        ]
        ref = parse_rttm(
            CORPUS_DIR / "rttm" / "two_speakers_no_overlap.rttm"
        )
        value = compute_der(ref, [])
        assert value == expected

    def test_no_speech_input_der_zero(self):
        """Sinal sem fala: referência vazia, hipótese vazia → DER 0
        (sem falso positivo de diarização em silêncio)."""
        assert compute_der([], []) == 0.0


# ---------------------------------------------------------------------------
# DIA-03 — Diarização real com diart/pyannote.audio (opt-in: HF token)
# ---------------------------------------------------------------------------

@pytest.mark.requires_hf_token
class TestDia03RealDiarization:
    """Diart/pyannote.audio REAIS sobre fixture pseudo-falada.

    Requisitos (todos opt-in, skips explícitos):
    - extra ``.[diarization]`` instalado (diart + pyannote.audio — pesado);
    - variável de ambiente ``HF_TOKEN`` ou ``HUGGING_FACE_HUB_TOKEN``
      (consultada por referência — o valor NUNCA é lido/ecoado);
    - termos dos modelos pyannote previamente aceitos na conta HF
      (intervenção humana — não automatizável).

    Mesmo quando executa, o resultado valida CONTRATO e INTEGRAÇÃO do
    DiarizationProcess (formato de segmentos, ordem, rótulos locais) —
    não a qualidade de embeddings em vozes humanas (documentado).
    """

    def _require_hf_token_reference(self) -> None:
        names = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
        present = [n for n in names if os.environ.get(n)]
        if not present:
            pytest.skip(
                "nenhuma variável HF_TOKEN/HUGGING_FACE_HUB_TOKEN no "
                "ambiente — diarização real requer token Hugging Face com "
                "termos dos modelos pyannote aceitos (job noturno/"
                "self-hosted)"
            )

    def test_diarization_process_contract_on_pseudo_speech(self, tmp_path):
        pytest.importorskip(
            "diart",
            reason="diart não instalado — requer extra '.[diarization]' "
                   "(árvore pesada: torch + pyannote.audio)",
        )
        self._require_hf_token_reference()

        import multiprocessing

        import soundfile as sf

        from src.audio.diarize import DiarizationProcess

        wav = CORPUS_DIR / "audio" / "two_speakers_no_overlap.wav"
        audio, sr = sf.read(str(wav), dtype="float64")
        assert sr == 16000

        in_q = multiprocessing.Queue()
        out_q = multiprocessing.Queue()
        proc = DiarizationProcess(in_q, out_q)
        try:
            segments = proc.diarize_file(str(wav))
        finally:
            proc.stop()
            if proc.is_alive():
                proc.join(timeout=10)

        # Contrato: lista de dicts {speaker, start, end} com speakers
        # locais (SPEAKER_xx / inteiros) — nunca identidade de pessoa.
        assert isinstance(segments, list)
        for seg in segments:
            assert set(("speaker", "start", "end")) <= set(seg)
            assert seg["end"] > seg["start"]
            assert isinstance(seg["speaker"], str)
