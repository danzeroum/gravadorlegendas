"""STT-01..STT-04 — Qualidade de transcrição: WER/CER objetivos.

Classificação honesta (ver docs/qualidade-audio/README.md):

- STT-01 (sintético/offline): testes unitários da normalização e da
  métrica WER/CER com pares de texto conhecidos — rodam sempre.
- STT-02 (sintético/offline): regressão da infraestrutura — degradações
  controladas de texto devem produzir WER/CER nas faixas esperadas.
- STT-03 (requer-modelo): STT real com faster-whisper ``base`` CPU sobre
  TTS determinístico (espeak-ng pt-br). Opt-in via marker
  ``requires_stt_model`` — skip explícito sem modelo/espeak. Thresholds
  calibrados por medição real local (manifesto, seção ``wer_policy``).
- STT-04 (hardware): o smoke test antigo de termos
  (tests/integration/test_e2e_stt_quality_real.py) é PRESERVADO sem
  alteração como teste de integração de pipeline real com PipeWire.

LIMITAÇÃO DECLARADA: TTS espeak não é fala humana — WER medido aqui é
representativo da consistência do pipeline em voz sintética robótica,
não do WER esperado em reuniões reais. Corpus consentido humano é
lacuna aberta (ver README §6).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.fidelity.text_metrics import cer, normalize_pt, wer, wer_cer
from tests.fixtures import signal_generators as sg

pytestmark = pytest.mark.fidelity

SR = 16000
REFERENCE = "teste de transcrição local no Fedora"


# ---------------------------------------------------------------------------
# STT-01 — Normalização documentada + métricas em pares conhecidos
# ---------------------------------------------------------------------------

class TestStt01Normalization:
    def test_casefold_applied(self):
        assert normalize_pt("TESTE De Transcrição") == "teste de transcricao"

    def test_punctuation_removed(self):
        assert normalize_pt("Teste, de transcrição! Local? No... Fedora.") == (
            "teste de transcricao local no fedora"
        )

    def test_diacritics_removed_by_default(self):
        assert normalize_pt("transcrição ação coração") == (
            "transcricao acao coracao"
        )

    def test_diacritics_kept_when_requested(self):
        assert normalize_pt("transcrição", keep_diacritics=True) == (
            "transcrição"
        )

    def test_punctuation_kept_when_requested(self):
        assert normalize_pt("oi, tudo?", keep_punctuation=True) == "oi, tudo?"

    def test_numbers_kept_literally(self):
        assert normalize_pt("reunião às 14 horas sala 3") == (
            "reuniao as 14 horas sala 3"
        )

    def test_whitespace_collapsed(self):
        assert normalize_pt("  muitos   espaços \n\t aqui ") == (
            "muitos espacos aqui"
        )

    def test_empty_string(self):
        assert normalize_pt("") == ""

    @settings(max_examples=50, deadline=None)
    @given(st.text(min_size=0, max_size=200))
    def test_normalization_is_idempotent(self, text):
        """normalize(normalize(x)) == normalize(x) — propriedade."""
        once = normalize_pt(text)
        assert normalize_pt(once) == once

    @settings(max_examples=25, deadline=None)
    @given(st.text(min_size=1, max_size=100))
    def test_wer_self_is_zero(self, text):
        """WER de qualquer texto contra si mesmo é 0 (após normalização)."""
        assert wer(text, text) == 0.0


class TestStt01WerCerMetrics:
    def test_perfect_transcription(self):
        assert wer(REFERENCE, "Teste de transcrição local no Fedora.") == 0.0
        assert cer(REFERENCE, "Teste de transcrição local no Fedora.") == 0.0

    def test_one_substitution_of_six_words(self):
        hyp = "teste de transcrição local no Fedoda"
        assert wer(REFERENCE, hyp) == pytest.approx(1.0 / 6.0)

    def test_deletion_counts(self):
        hyp = "teste de transcrição local"
        assert wer(REFERENCE, hyp) == pytest.approx(2.0 / 6.0)  # 2 de 6 ausentes

    def test_insertion_counts(self):
        hyp = "teste de transcrição local no Fedora agora"
        assert wer(REFERENCE, hyp) == pytest.approx(1.0 / 6.0)

    def test_totally_wrong_is_one(self):
        assert wer(REFERENCE, "xkwq zvppl mnbc") == 1.0

    def test_empty_hypothesis(self):
        assert wer(REFERENCE, "") == 1.0

    def test_cer_less_than_wer_for_small_errors(self):
        """CER detecta erros parciais dentro da palavra (Fedora->Fedoda)."""
        hyp = "Teste de transcrição local no Fedoda"
        assert cer(REFERENCE, hyp) < wer(REFERENCE, hyp)
        assert cer(REFERENCE, hyp) == pytest.approx(
            1.0 / len(normalize_pt(REFERENCE)), abs=1e-9
        )

    def test_wer_cer_bundle(self):
        result = wer_cer(REFERENCE, REFERENCE)
        assert result == {"wer": 0.0, "cer": 0.0}


# ---------------------------------------------------------------------------
# STT-02 — Regressão sintética da infraestrutura de métrica
# ---------------------------------------------------------------------------

class TestStt02SyntheticRegression:
    """Degradações controladas de texto → WER/CER nas faixas esperadas.

    Isso valida que a métrica DETECTA regressões de qualidade (o teste
    falharia se a métrica parasse de funcionar — não tautológico).
    """

    def test_metric_detects_word_swap(self):
        good = "teste de transcrição local no fedora"
        bad = "teste de captura local no fedora"
        assert wer(REFERENCE, good) < wer(REFERENCE, bad)

    def test_metric_detects_progressive_degradation(self):
        words = normalize_pt(REFERENCE).split()
        wers = []
        for n_drop in range(len(words) + 1):
            degraded = " ".join(words[: len(words) - n_drop])
            wers.append(wer(REFERENCE, degraded))
        assert wers == sorted(wers), (
            "WER deveria crescer monotonicamente com a degradação"
        )

    def test_category_thresholds_from_manifest(self, corpus_manifest):
        """Categorias do manifesto: limiares presentes e coerentes
        (clean < low_volume < moderate_noise em tolerância ao ruído)."""
        cats = corpus_manifest["wer_policy"]["categories"]
        assert 0.0 <= cats["clean"]["wer_max"] < 1.0
        assert cats["clean"]["wer_max"] < cats["moderate_noise"]["wer_max"]
        assert cats["low_volume"]["wer_max"] < cats["moderate_noise"][
            "wer_max"
        ]

    def test_known_degradations_within_expected_bands(self):
        """Banda esperada: 1 erro em 6 palavras → WER ≈ 0.167."""
        one_error = "teste de transcrição local no Fedoda"
        assert 0.0 < wer(REFERENCE, one_error) <= 0.18


# ---------------------------------------------------------------------------
# STT-03 — STT real com faster-whisper (opt-in: requires_stt_model)
# ---------------------------------------------------------------------------

def _require_espeak() -> None:
    if not shutil.which("espeak-ng"):
        pytest.skip("espeak-ng não disponível — TTS determinístico não gerável")


def _require_whisper_base() -> None:
    pytest.importorskip(
        "faster_whisper",
        reason="faster-whisper não instalado — STT real indisponível",
    )
    from src.audio.transcribe import whisper_model_dir

    if not whisper_model_dir("base").exists():
        pytest.skip(
            "modelo faster-whisper 'base' não está em cache "
            "(~/.cache/gravador/audio/whisper) — rode o setup do produto "
            "(scripts/setup_audio_models.py) ou o job noturno de qualidade"
        )


def _tts_reference(tmp_path: Path) -> np.ndarray:
    """Gera a frase de referência com espeak-ng (determinístico)."""
    wav = tmp_path / "referencia.wav"
    cmd = [
        "espeak-ng", "-v", "pt-br", "-s", "90", "-g", "8",
        "-w", str(wav), REFERENCE,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        pytest.skip(f"espeak-ng falhou: {r.stderr[:200]}")
    import soundfile as sf

    audio, rate = sf.read(str(wav), dtype="float64")
    if rate != SR:
        audio = sg.resample(audio, rate, SR)
    return np.clip(audio, -1.0, 1.0)


@pytest.mark.requires_stt_model
class TestStt03RealModelWer:
    """WER/CER reais com faster-whisper base CPU + TTS determinístico.

    Sem hardware de áudio: o áudio entra direto no modelo (mesmo caminho
    de inferência do TranscriberProcess do produto). Thresholds por
    categoria calibrados no manifesto (wer_policy) a partir de medição
    local documentada.
    """

    @pytest.fixture()
    def whisper_model(self):
        _require_espeak()
        _require_whisper_base()
        from faster_whisper import WhisperModel
        from src.audio.transcribe import WHISPER_DOWNLOAD_ROOT

        return WhisperModel(
            "base", device="cpu", download_root=str(WHISPER_DOWNLOAD_ROOT),
        )

    @staticmethod
    def _transcribe(model, sig: np.ndarray) -> str:
        segments, _ = model.transcribe(
            sig.astype(np.float32), language="pt", beam_size=1,
            temperature=0.0, vad_filter=True,
        )
        return " ".join(
            (s.text or "").strip() for s in segments if (s.text or "").strip()
        )

    def test_wer_clean_category(self, whisper_model, tmp_path,
                                corpus_manifest):
        """Clean: WER ≤ 0.20, CER ≤ 0.15 (calibrado: medido 0.000/0.000)."""
        audio = _tts_reference(tmp_path)
        text = self._transcribe(whisper_model, audio)
        thresholds = corpus_manifest["wer_policy"]["categories"]["clean"]
        print(f"\n[STT-03 clean] {text!r}")
        m = wer_cer(REFERENCE, text)
        print(f"[STT-03 clean] WER={m['wer']:.3f} CER={m['cer']:.3f} "
              f"(limiares {thresholds})")
        assert m["wer"] <= thresholds["wer_max"], (
            f"WER clean {m['wer']:.3f} > {thresholds['wer_max']}"
        )
        assert m["cer"] <= thresholds["cer_max"]

    def test_wer_low_volume_category(self, whisper_model, tmp_path,
                                     corpus_manifest):
        """Low volume (0.25x): WER ≤ 0.40 (calibrado: medido 0.167)."""
        audio = _tts_reference(tmp_path) * 0.25
        text = self._transcribe(whisper_model, audio)
        thresholds = corpus_manifest["wer_policy"]["categories"]["low_volume"]
        print(f"\n[STT-03 low_volume] {text!r}")
        m = wer_cer(REFERENCE, text)
        print(f"[STT-03 low_volume] WER={m['wer']:.3f} CER={m['cer']:.3f} "
              f"(limiares {thresholds})")
        assert m["wer"] <= thresholds["wer_max"], (
            f"WER low_volume {m['wer']:.3f} > {thresholds['wer_max']}"
        )

    def test_wer_moderate_noise_category(self, whisper_model, tmp_path,
                                         corpus_manifest):
        """Moderate noise (SNR 10 dB): WER ≤ 0.70 (calibrado: 0.500)."""
        audio = _tts_reference(tmp_path)
        noisy = sg.add_noise(audio, snr_db=10.0, seed=99)
        text = self._transcribe(whisper_model, noisy)
        thresholds = corpus_manifest["wer_policy"]["categories"][
            "moderate_noise"
        ]
        print(f"\n[STT-03 moderate_noise] {text!r}")
        m = wer_cer(REFERENCE, text)
        print(f"[STT-03 moderate_noise] WER={m['wer']:.3f} "
              f"CER={m['cer']:.3f} (limiares {thresholds})")
        assert m["wer"] <= thresholds["wer_max"], (
            f"WER moderate_noise {m['wer']:.3f} > {thresholds['wer_max']}"
        )


# ---------------------------------------------------------------------------
# STT-04 — Smoke test antigo preservado (contrato de não-regressão)
# ---------------------------------------------------------------------------

class TestStt04LegacySmokePreserved:
    def test_legacy_term_count_smoke_still_exists(self):
        """O smoke test antigo (contagem de termos) permanece no repositório
        como teste de integração real com PipeWire — inalterado."""
        legacy = (
            Path(__file__).resolve().parent.parent / "integration"
            / "test_e2e_stt_quality_real.py"
        )
        assert legacy.exists(), (
            "smoke test legado de STT foi removido — regressão de cobertura!"
        )
        content = legacy.read_text(encoding="utf-8")
        assert "REFERENCE_PHRASE" in content
        assert "requires_stt_model" in content
        assert "MIN_TARGET_TERMS" in content
