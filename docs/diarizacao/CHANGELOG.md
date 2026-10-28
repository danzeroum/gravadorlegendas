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

---

## 2026-10-28 — Frente H1: ferramentas de medição e baseline

**Descrição:**
- `tests/fidelity/text_metrics.py`: `cp_wer` (associação ótima de falantes
  via `linear_sum_assignment`) e `speaker_coverage`.
- `src/audio/rttm.py`: leitura/escrita de RTTM compartilhada (o parser do
  teste DIA não podia ser importado fora do pytest por causa do
  `importorskip` de módulo).
- `src/audio/file_decode.py`: `decode_to_wav16k` com PyAV (mp3, m4a, mp4,
  ogg/opus, flac, webm, wav → WAV 16 kHz mono). Base de IMP-01 (Frente J).
- `scripts/corpus_real.py`: `init/add/import-labels/verify/purge`; recusa
  diretório dentro do repo; sha256, consentimento e retenção por item.
- `scripts/eval_diarization.py`: pipelines `oracle`, `rttm`, `current`,
  `offline`; DER e componentes via `pyannote.metrics`; cpWER e cobertura
  quando há palavras; `--compare` com exit ≠0 em regressão. JSON só com IDs
  e números.

**Arquivos:** os acima + `tests/fidelity/test_speaker_text_metrics.py`,
`tests/test_corpus_real.py`, `tests/test_eval_diarization.py`,
`tests/test_file_decode.py`, `tests/media_fixtures.py`.

**Comandos:**

```text
pytest tests/test_eval_diarization.py tests/test_corpus_real.py \
       tests/fidelity/test_speaker_text_metrics.py tests/test_file_decode.py -q
  -> 37 passed   (com pyannote.metrics 4.2.0 e PyAV 18.1.0 instalados)

python scripts/eval_diarization.py --corpus tests/fixtures/corpus --pipeline oracle
  pipeline=oracle corpus=corpus ok=4 erro=0
    der: 0.0000  confusion: 0.0000  false_alarm: 0.0000  missed: 0.0000

python scripts/eval_diarization.py --corpus tests/fixtures/corpus --pipeline current
  pipeline=current corpus=corpus ok=0 erro=4
    ERRO two_speakers_no_overlap: RuntimeError: diart não instalado. pip install diart
    (idem nos 4 cenários)
```

**Baseline (AVL-05):** o pipeline atual **não é executável** neste ambiente
— exige diart + modelo `pyannote/embedding` (gated, `HF_TOKEN`). O harness
está validado pelo `oracle` (DER 0) e pelo `rttm` deslocado (DER detectado).
A medição do pipeline atual fica para quem tiver token:
`python scripts/eval_diarization.py --corpus tests/fixtures/corpus --pipeline current --out base.json`.
Corpus real: nenhum disponível neste ambiente (esperado — R3).

**Requisitos:** AVL-01..04 → `validated-local`; AVL-05 → `skipped-no-model`.

---

## 2026-10-28 — Frente E: diarizador offline + falante nas legendas

**Descrição:** `OfflineDiarizer` (pyannote.audio 3.x/4.x), `make_exclusive`,
`normalize_labels`, `check_ready` com mensagens acionáveis; `diarize_file`
delega a ele (D-018). `CaptionSegment.speaker`; exportador SRT/VTT/TXT com
nomes (D-019). Config `DIARIZATION_MODEL`, `DIARIZATION_DEVICE`,
`DIARIZATION_EXCLUSIVE`. Teste real DIA-03 passou a exigir `pyannote.audio`
(não diart) e ganhou DIA-09 (DER do `OfflineDiarizer` real).

Ajuste de ordem: a flag `--diarize` do `transcribe_file.py` entra na Frente
F, já com atribuição por palavra, para não implementar a atribuição por
segmento e trocá-la em seguida.

**Arquivos:** `src/audio/offline_diarizer.py`, `src/audio/diarize.py`,
`src/audio/models.py`, `src/storage/subtitle_exporter.py`, `src/config.py`,
`.env.example`, `tests/test_offline_diarizer.py`,
`tests/test_subtitle_exporter.py`, `tests/fidelity/test_diarization_der.py`.

**Comandos:**

```text
pytest tests/test_offline_diarizer.py -q            -> 17 passed
pytest tests/fidelity/test_diarization_der.py -q -rs
  -> 33 passed, 2 skipped (sem HF_TOKEN — DIA-03 e DIA-09)
pytest tests/ -q
  -> 2 failed (test_ocr: Tesseract ausente, preexistente), 555 passed, 47 skipped
```

Validação contra a API real: pyannote.audio 4.0.7 instalado;
`Pipeline.from_pretrained(..., token=, cache_dir=)` e `DiarizeOutput`
conferidos; sem token o carregamento do modelo falha com "gated repo",
convertido em `DiarizationUnavailable`.

**Requisitos:** DIA-04..08 → `validated-local`; DIA-09 → `skipped-no-model`.

---

## 2026-10-28 — Frente F: atribuição de falante por palavra

**Descrição:**
- `src/audio/speaker_assignment.py`: `Word`, `assign_words` (ponto médio,
  tolerância de 0,3 s, sobreposição → quem começou por último, O((n+m) log m))
  e `group_segments` (quebra por falante, pausa > 1 s ou legenda > 7 s;
  palavra sem falante não quebra o grupo).
- Ao vivo: `TranscriberProcess(word_timestamps=...)` emite `"words"` com
  tempo absoluto; `AudioManager` liga quando a diarização está ativa e
  emite um trecho por falante (best effort; offline é a fonte de verdade).
  Exportação ao vivo usa `SubtitleExporter.save_txt` (falante no .txt).
- `OverlapCounter`: varredura de eventos, só falantes distintos (ACH-05).
- `src/audio/file_pipeline.py` (`transcribe_audio_file`): decodificar →
  Whisper com tempo por palavra → diarizar → atribuir → agrupar; progresso
  e cancelamento; sem diarização disponível, transcreve e explica o motivo.
  Antecipa J.a (IMP-02/IMP-04) para a CLI e a UI usarem o mesmo código.
- `scripts/transcribe_file.py`: `--diarize`, `--num-speakers`,
  `--min-speakers`, `--max-speakers`, `--speaker-map`; `--diarize` falha
  antes de carregar o Whisper se a diarização não estiver pronta.
- `scripts/eval_diarization.py`: pipeline `offline+words`.

**Arquivos:** os acima + `tests/test_speaker_assignment.py`,
`tests/test_live_word_speakers.py`, `tests/test_file_pipeline.py`,
`tests/test_audio_metrics.py`.

**Comandos:**

```text
pytest tests/test_speaker_assignment.py -q   -> 12 passed
pytest tests/test_live_word_speakers.py -q   -> 4 passed
pytest tests/test_file_pipeline.py -q        -> 10 passed
pytest tests/test_audio_metrics.py -q        -> 17 passed
pytest tests/ -q
  -> 2 failed (test_ocr: Tesseract ausente, preexistente), 588 passed, 44 skipped
python scripts/eval_diarization.py --corpus tests/fixtures/corpus --pipeline offline+words
  -> ok=0 erro=4 (DiarizationUnavailable: token do Hugging Face ausente…)
```

Ganho de DER/cpWER **não medido** neste ambiente (sem token HF): rodar
`eval_diarization.py --pipeline offline` e `--pipeline offline+words` com
token e `--compare` antes de declarar ganho (D-023).

**Requisitos:** ALN-01..06 → `validated-local`.
