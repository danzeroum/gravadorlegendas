"""Métricas textuais (WER/CER) com normalização documentada para PT-BR.

Decisões de normalização (ver docs/qualidade-audio/DECISOES.md D-001):

1. **Case**: ``casefold()`` (mais agressivo e correto que ``lower()``
   para comparação linguística).
2. **Pontuação**: removida (substituída por espaço) e espaços colapsados
   — pontuação é ruído para WER de ASR.
3. **Diacríticos**: REMOVIDOS por padrão (NFD + remoção de combining
   marks). Justificativa: ASRs são inconsistentes em acentuação
   ("transcrição" vs "transcricao") e o objetivo da métrica é medir
   erro de *palavra*, não erro de acento. A opção ``keep_diacritics``
   existe para análise estrita.
4. **Números**: mantidos literalmente (dígitos preservados) — decisão
   documentada; normalização numérica ("2" ↔ "dois") introduziria
   ambiguidade sem ganho de mensuração.
5. **Espaços**: colapsados para um único espaço; vazios à direita/
   esquerda removidos.

Uso:
    >>> from tests.fidelity.text_metrics import wer, cer, normalize_pt
    >>> round(wer("teste de transcrição", "teste de transcricao"), 3)
    0.0
"""
from __future__ import annotations

import unicodedata

import jiwer


def normalize_pt(
    text: str,
    *,
    keep_diacritics: bool = False,
    keep_punctuation: bool = False,
) -> str:
    """Normaliza texto PT-BR para comparação de WER/CER.

    Ver docstring do módulo para as decisões de normalização.
    """
    if not text:
        return ""
    # 1) Casefold
    out = text.casefold()
    # 2) Diacríticos (NFD + remove combining marks)
    if not keep_diacritics:
        out = unicodedata.normalize("NFD", out)
        out = "".join(
            ch for ch in out if unicodedata.category(ch) != "Mn"
        )
        out = unicodedata.normalize("NFC", out)
    # 3) Pontuação
    if not keep_punctuation:
        out = "".join(
            ch if ch.isalnum() or ch.isspace() else " " for ch in out
        )
    # 4) Colapsa espaços
    return " ".join(out.split())


def _prepare(
    reference: str,
    hypothesis: str,
    **norm_kwargs,
) -> tuple[str, str]:
    ref = normalize_pt(reference, **norm_kwargs)
    hyp = normalize_pt(hypothesis, **norm_kwargs)
    return ref, hyp


def wer(reference: str, hypothesis: str, **norm_kwargs) -> float:
    """Word Error Rate entre referência e hipótese (0.0 = perfeito)."""
    ref, hyp = _prepare(reference, hypothesis, **norm_kwargs)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.wer(ref, hyp))


def cer(reference: str, hypothesis: str, **norm_kwargs) -> float:
    """Character Error Rate entre referência e hipótese (0.0 = perfeito).

    Computado sobre o texto normalizado (espaços internos preservados
    como caractere único — espaço é token válido de CER).
    """
    ref, hyp = _prepare(reference, hypothesis, **norm_kwargs)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.cer(ref, hyp))


def wer_cer(
    reference: str,
    hypothesis: str,
    **norm_kwargs,
) -> dict[str, float]:
    """Pacote WER+CER para relatórios JSON."""
    return {
        "wer": wer(reference, hypothesis, **norm_kwargs),
        "cer": cer(reference, hypothesis, **norm_kwargs),
    }


# ---------------------------------------------------------------------------
# Métricas com falante (docs/diarizacao, Frente H1)
# ---------------------------------------------------------------------------

def _word_errors(ref: str, hyp: str) -> int:
    """Substituições + deleções + inserções (palavras) entre textos já
    normalizados. Vazios tratados à parte (jiwer exige referência)."""
    ref_n = len(ref.split())
    hyp_n = len(hyp.split())
    if ref_n == 0:
        return hyp_n
    if hyp_n == 0:
        return ref_n
    out = jiwer.process_words(ref, hyp)
    return int(out.substitutions + out.deletions + out.insertions)


def cp_wer(
    reference: dict[str, str],
    hypothesis: dict[str, str],
    **norm_kwargs,
) -> float:
    """Concatenated minimum-permutation WER (cpWER).

    Args:
        reference: falante -> texto concatenado de todas as falas dele.
        hypothesis: idem, com os rótulos da diarização (IDs locais).

    Monta a matriz de erros ref_i × hyp_j (completada com falantes vazios
    até ficar quadrada) e escolhe a associação de falantes de menor erro
    total (``scipy.optimize.linear_sum_assignment``). Rótulos trocados de
    forma consistente não contam como erro; falante a mais ou a menos na
    hipótese conta suas palavras como inserção ou deleção.

    Returns:
        erros_totais / palavras_da_referência (0.0 = perfeito).
    """
    from scipy.optimize import linear_sum_assignment

    refs = [normalize_pt(t, **norm_kwargs) for t in reference.values()]
    hyps = [normalize_pt(t, **norm_kwargs) for t in hypothesis.values()]
    size = max(len(refs), len(hyps), 1)
    refs += [""] * (size - len(refs))
    hyps += [""] * (size - len(hyps))

    total_ref_words = sum(len(r.split()) for r in refs)
    cost = [[_word_errors(r, h) for h in hyps] for r in refs]
    rows, cols = linear_sum_assignment(cost)
    errors = sum(cost[i][j] for i, j in zip(rows, cols))
    if total_ref_words == 0:
        return 0.0 if errors == 0 else 1.0
    return errors / total_ref_words


def speaker_coverage(speakers: list) -> float:
    """Fração de palavras que receberam falante (``None`` = sem rótulo)."""
    if not speakers:
        return 0.0
    return sum(1 for s in speakers if s is not None) / len(speakers)
