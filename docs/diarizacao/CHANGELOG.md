# CHANGELOG — Diarização e Atribuição de Falantes

Formato: data UTC, descrição objetiva, arquivos, comandos executados e
resultado colado da saída. Plano: `PLANO-IMPLEMENTACAO.md`.

---

## 2026-10-28 — Linha de base

**Ambiente:** container Linux, Python 3.11 (igual ao CI), deps de
`requirements.txt` (torch CPU) + `jiwer hypothesis PyYAML jsonschema
numpy==2.1.3 scipy==1.14.1 soundfile==0.13.1 faster-whisper av`. Sem
Tesseract, sem pyannote, sem token HF, sem hardware de áudio.

**Comandos:**

```text
pytest tests/ -q
  2 failed, 442 passed, 46 skipped
  FAILED tests/test_ocr.py::TestOCREngine::test_extract_text_returns_string
  FAILED tests/test_ocr.py::TestOCREngine::test_extract_text_empty_on_blank
  (binário Tesseract ausente no container — preexistente, fora do escopo)
flake8 src/ --max-line-length=100 --extend-ignore=E501,W503,E203
  (sem saída)
```

---

## 2026-10-28 — Frente E0: guarda de privacidade

**Descrição:** `scripts/secret_scan_changed_files.py` ganhou checagem por
caminho (`classify_path`): áudio fora de `tests/fixtures/corpus/audio/`,
RTTM fora de `tests/fixtures/corpus/rttm/` e qualquer caminho com
`voiceprint` reprovam. Novo modo `--tracked-paths` (sobre `git ls-files`),
executado no job `lint` do `ci.yml`. `.gitignore` cobre `corpus_real/`,
`voiceprints*` e `*.rttm` (com exceção do corpus sintético).

**Arquivos:** `scripts/secret_scan_changed_files.py`, `.gitignore`,
`.github/workflows/ci.yml`, `tests/test_privacy_guard.py`.

**Comandos:**

```text
pytest tests/test_privacy_guard.py -q          -> 18 passed
python scripts/secret_scan_changed_files.py --tracked-paths
  -> Nenhum áudio, RTTM ou voiceprint fora do corpus sintético.
```

**Requisitos:** PRIV-01, PRIV-02, PRIV-03 → `validated-local`.

---

## 2026-10-28 — Frente E1: fan-out de filas (ACH-01)

**Descrição:** diarizador ganhou fila própria (`_diarization_audio_queue`);
`_fanout_loop` publica em Whisper e diarizador. Diarizador e WAV de
reprocessamento recebem áudio sem RNNoise (D-017).

**Arquivos:** `src/audio/manager.py`, `tests/test_audio_fanout.py`,
`docs/diarizacao/DECISOES.md`.

**Comandos:**

```text
# sem a correção (git stash):
pytest tests/test_audio_fanout.py -q  -> 3 failed, 1 passed
# com a correção:
pytest tests/test_audio_fanout.py tests/test_audio_manager.py \
       tests/test_live_subtitle_export.py -q  -> 20 passed
```

**Requisitos:** FILA-01, FILA-02 → `validated-local`.
