# PLANO DE IMPLEMENTAÇÃO — Diarização e Atribuição de Falantes

Plano executável por um agente (ou contributor) para levar o
`gravadorlegendas` de "transcrição com rótulo de falante aproximado" para
"transcrição com falante por palavra, medida contra referência".

Segue as convenções de `docs/qualidade-audio/` (IDs estáveis, matriz de
status, decisões numeradas, CHANGELOG com evidência). **Leia este documento
inteiro antes do primeiro commit.**

---

## 0. Instruções ao agente (resumo operacional)

1. Trabalhe uma **frente por PR**, na ordem da §4. Não comece uma frente cuja
   dependência não esteja `validated-ci`.
2. Antes de codar, rode a linha de base: `pytest tests/ -q` e
   `flake8 src/ --max-line-length=100 --extend-ignore=E501,W503,E203`.
   Registre o resultado no CHANGELOG desta pasta.
3. **Reaproveite, não duplique** (§2). Se for criar um módulo novo, justifique
   no PR por que nenhum existente serve.
4. Toda mudança de comportamento tem teste. Deps pesadas (pyannote, diart,
   torch, faster-whisper) entram por `pytest.importorskip` ou marker
   `requires_hf_token` — o job de PR continua leve (D-010).
5. **Ganho se mede, não se estima.** Nenhum número de DER/WER em PR, doc ou
   commit sem a saída do comando que o gerou.
6. Atualize, no mesmo PR: a matriz da §5 (status), `DECISOES.md` desta pasta
   quando tomar decisão de design, e o `CHANGELOG.md` desta pasta.
7. Commits no padrão do repo: `feat(diarize): ...`, `fix(audio): ...`,
   `test(fidelity): ...`, `docs(diarizacao): ...`.
8. Regras invioláveis (§3). Violar qualquer uma é motivo para reverter o PR.

---

## 1. Diagnóstico — achados confirmados no código

Lidos em `main@4fa4009`. Cada achado vira requisito na matriz (§5).

| ID | Achado | Onde | Gravidade |
|---|---|---|---|
| ACH-01 | **Transcriber e diarizador consomem a MESMA `multiprocessing.Queue`.** Cada chunk vai para só um dos dois processos: com diarização ativa, o Whisper perde áudio e o diart recebe áudio picotado. | `src/audio/manager.py` (`self._audio_queue` passado a `TranscriberProcess` e a `DiarizationProcess`) | **Crítica** |
| ACH-02 | `DiarizationProcess.diarize_file` usa `OnlineSpeakerDiarization` do diart com `AudioFileSource` — não é diarização offline com pyannote, embora o README prometa `pyannote/speaker-diarization-3.1`. | `src/audio/diarize.py` | Alta |
| ACH-03 | Atribuição de falante por **lote inteiro** (~7 s): `_match_speaker(result.start, result.end)` dá um único rótulo para um lote com várias pessoas. | `src/audio/manager.py::_match_speaker` | Alta |
| ACH-04 | `scripts/transcribe_file.py` não pede `word_timestamps` nem diariza — a saída offline não tem falante. | `scripts/transcribe_file.py` | Alta |
| ACH-05 | `OverlapCounter` é O(n²) e conta como sobreposição dois segmentos do **mesmo** falante. | `src/audio/metrics.py` | Média |
| ACH-06 | Com `AUDIO_SOURCE=both` (mixer ativo), o `DualTrackRecorder` grava só o trilho **mixado** no `mic_path` e deixa o do sistema vazio — destrói a separação por canal, que é a pista mais barata para diarizar. | `src/audio/manager.py::_fanout_loop` | Alta |
| ACH-07 | O offset entre trilhos (`mic_start_monotonic` / `system_start_monotonic`) existe em `DualTrackResult` mas não é persistido em disco — o reprocessamento offline não consegue alinhar as duas faixas. | `src/audio/recorder.py` | Média |
| ACH-08 | `CaptionSegment` não tem campo de falante; SRT/VTT/TXT saem sem `[Nome]`. | `src/audio/models.py`, `src/storage/subtitle_exporter.py` | Média |
| ACH-09 | `secret_scan_changed_files.py` não bloqueia áudio nem voiceprints commitados. | `scripts/secret_scan_changed_files.py` | Média (bloqueante antes de corpus real) |
| ACH-10 | Fallback espectral do `RNNoiseFilter` degrada SNR de fala em ~7,3 dB (D-009). | `src/filter/noise_suppression.py` | Restrição de design |

---

## 2. Inventário de reaproveitamento

| Necessidade | Reaproveitar | Não criar |
|---|---|---|
| Métrica DER | `tests/fidelity/test_diarization_der.py` (`parse_rttm`, `pyannote.metrics`), `scripts/measure_der_baseline.py` | notebook de avaliação |
| Métrica WER/CER | `tests/fidelity/text_metrics.py`, `jiwer` (extra `fidelity`) | nova lib de métrica |
| Corpus + orçamentos | `tests/fixtures/corpus/manifest.yaml` (`der_policy`, `wer_policy`, `budgets`), `scripts/gen_fidelity_fixtures.py` | outro formato de manifest |
| Golden/hashes | `scripts/fidelity_golden.py` (sha256, freeze/verify) | lockfile próprio sem sha256 |
| Relatório | `scripts/build_fidelity_report.py` + `schemas/audio-fidelity-report-v1.json` | schema v2 / migrador |
| Gravação por canal | `src/audio/recorder.py::DualTrackRecorder` | captura nova |
| Transcrição offline | `scripts/transcribe_file.py` (`collect_inputs`, `load_model`, `write_outputs`) | `transcrever.py` paralelo |
| Exportação | `src/storage/subtitle_exporter.py`, `CaptionSegment` | formatter novo |
| Nomes de falantes | `results_panel.get_speaker_map()` / `load_speaker_map()` (`{sid: {name, color}}`), `tests/test_speaker_map_persistence.py` | `speaker_mapping.py` com outro formato |
| Diagnóstico de ambiente | `scripts/diagnose_linux_audio.py`, `scripts/setup_audio_models.py` | CLI `agent check-env` |
| Scan de segredos | `scripts/secret_scan_changed_files.py` | scanner separado |
| Plugabilidade | padrão de `src/caption/factory.py` / `src/llm/registry.py` | framework de plugins |

---

## 3. Regras invioláveis

- **R1 — 16 kHz mono PCM s16le** em todo o pipeline (captura, corpus, diarização,
  ASR). Nada de 48 kHz.
- **R2 — Sem denoise antes da diarização.** O `RNNoiseFilter` não pode estar no
  caminho do áudio que alimenta o diarizador offline. Diarização lê os WAVs
  brutos do `DualTrackRecorder` (ACH-10 / D-009).
- **R3 — Nenhum áudio real, transcrição real, RTTM real ou voiceprint no git.**
  Corpus real vive fora do repositório (§4, Frente H1). O CI só usa o corpus
  sintético.
- **R4 — Token HF só por variável de ambiente** (`HF_TOKEN`), nunca logado,
  nunca em arquivo versionado. Mensagens de erro citam o nome da variável, não
  o valor.
- **R5 — Deps opcionais continuam opcionais.** Import pesado só dentro de
  função/método; testes com `importorskip`/marker. `pytest tests/` sem extras
  continua verde.
- **R6 — Retrocompatibilidade:** `CaptionSegment` continua desempacotável em
  `(start, end, text)`; `diarize_file()` continua retornando `list[dict]`
  `{speaker, start, end}`; `.env` antigo continua funcionando.
- **R7 — Skip honesto:** recurso ausente → skip com motivo; nunca `pass` vazio,
  nunca teste `TODO`.
- **R8 — Identificação de pessoa (voiceprint) só com a Frente I aprovada**
  (requisito explícito + RIPD + consentimento), conforme a ressalva já
  registrada em `test_diarization_der.py` e D-002.

---

## 4. Frentes de implementação

Ordem e dependências:

```text
E0 (privacidade) ─┐
E1 (fila)  ───────┼─► H1 (métricas + baseline) ─► E (diarizador offline) ─► F (palavra) ─┬─► G (2 faixas) ─► H2 (CI/report) ─► I (voiceprints, condicional)
                                                                                        └─► J (importar arquivo na UI)
```

J e G são independentes entre si: J pode ser entregue logo após F.

H1 vem antes de E de propósito: sem baseline medido, não há como provar que
E/F/G melhoraram algo.

---

### Frente E0 — Guarda de privacidade no CI

**Depende de:** nada. **Tamanho:** P.

**Mudanças**

1. `scripts/secret_scan_changed_files.py` — adicionar checagem de **caminho**
   (não de conteúdo):
   - Reprovar arquivos alterados com extensão em
     `{.wav, .mp3, .m4a, .mp4, .ogg, .flac, .webm, .opus}` fora de
     `tests/fixtures/corpus/audio/`.
   - Reprovar `*.rttm` fora de `tests/fixtures/corpus/rttm/`.
   - Reprovar qualquer caminho que contenha `voiceprint` (case-insensitive).
   - Saída no mesmo estilo: só nome do arquivo + regra, nunca conteúdo.
2. `.gitignore` — acrescentar `voiceprints*`, `*.rttm` com exceção
   `!tests/fixtures/corpus/rttm/*.rttm`, e `corpus_real/`.
3. Adicionar o script ao job de PR (`ci.yml`) — hoje ele **não** roda em
   nenhum workflow (`grep secret_scan .github/workflows/` vazio). O checkout
   precisa de `fetch-depth: 0` para o `git diff main...HEAD` funcionar.
   Editar workflow exige token com permissão `Workflows` (ver D-013).

**Testes** — `tests/test_privacy_guard.py`
- Função pura `classify_path(rel: str) -> str | None` (extraída do script) com
  casos: fixture permitida, `.wav` em `data/` (gitignored, mas se forçado →
  reprovado), `docs/x.m4a` reprovado, `src/voiceprints.json` reprovado,
  `tests/fixtures/corpus/rttm/a.rttm` permitido.

**Aceite:** PRIV-01..03 `validated-ci`.

---

### Frente E1 — Fan-out de filas (corrige ACH-01)

**Depende de:** nada. **Tamanho:** P.

**Mudanças** — `src/audio/manager.py`

- Criar `self._diarization_audio_queue: multiprocessing.Queue` separado.
- `DiarizationProcess(self._diarization_audio_queue, self._diarization_queue)`.
- Em `_fanout_loop`, após o processamento, publicar o chunk em
  `self._audio_queue` (Whisper) **e**, se `self._diarizer` estiver ativo, em
  `self._diarization_audio_queue`.
- O chunk que vai ao diarizador é o **pré-RNNoise** (R2): guardar referência
  ao chunk antes do `self._noise_filter.process_frame`.
- Esvaziar/fechar a fila nova em `stop()` como as demais.

**Testes** — `tests/test_audio_manager.py` (estender)
- Com diarização habilitada e processos mockados, N chunks injetados em
  `_master_queue` → **ambas** as filas recebem N chunks, em ordem.
- Com `noise_suppression=True` e filtro mock que inverte o sinal: fila do
  Whisper recebe o processado, fila do diarizador recebe o bruto.
- Com diarização desligada: fila do diarizador não recebe nada.

**Decisão a registrar:** D-017 (fan-out explícito, diarizador recebe áudio bruto).

**Aceite:** FILA-01..02 `validated-ci`.

---

### Frente H1 — Ferramentas de medição e baseline

**Depende de:** E0. **Tamanho:** M.

**H1.a — cpWER e métricas de atribuição** (`tests/fidelity/text_metrics.py`)

Funções puras, sem torch:

```python
def cp_wer(ref: dict[str, str], hyp: dict[str, str]) -> float:
    """Concatenated minimum-permutation WER.

    ref/hyp: falante -> texto concatenado de todas as falas dele.
    Monta a matriz de erros (jiwer) ref_i x hyp_j, completa com
    falantes vazios até ficar quadrada e resolve a permutação ótima com
    scipy.optimize.linear_sum_assignment. Retorna erros/palavras_ref.
    """

def speaker_coverage(words: list[dict]) -> float:
    """Fração de palavras com speaker != None."""
```

DER, confusão, falso alarme e perda continuam vindo de
`pyannote.metrics.diarization.DiarizationErrorRate` (detalhado com
`detailed=True`) — não reimplementar (D-002).

**H1.b — Corpus real local** (`scripts/corpus_real.py`)

Subcomandos:

| Comando | Faz |
|---|---|
| `init --dir PATH --name N` | Recusa `PATH` dentro do repo (`Path.resolve()` sob `ROOT` → erro). Cria `PATH/manifest.yaml` + `audio/` + `rttm/` + `transcripts/`. |
| `add --dir PATH --audio X.wav --rttm X.rttm [--transcript X.txt] --consent-ref ID --retain-until AAAA-MM-DD` | Converte para 16 kHz mono se preciso (ffmpeg/soundfile), copia, registra sha256, consentimento e retenção. |
| `import-labels --audacity labels.txt --out X.rttm` | Converte labels do Audacity (`start\tend\tSPEAKER`) para RTTM. ELAN: export "tab-delimited" no mesmo formato. |
| `verify --dir PATH` | Confere sha256, presença de consentimento, prazos não vencidos, e que `PATH` não está sob o repo. Sai ≠0 em qualquer falha. |
| `purge --dir PATH [--dry-run]` | Remove itens com `retain_until` vencido e atualiza manifest. |

Manifest (mesmo esqueleto do sintético, campos extras):

```yaml
schema: gravadorlegendas/corpus-real@1
contains_personal_audio: true
storage_note: "diretório em volume criptografado (LUKS/BitLocker) — responsabilidade do operador"
sample_rate: 16000
channels: 1
items:
  - id: reuniao_2026_10_01
    audio: audio/reuniao_2026_10_01.wav
    rttm: rttm/reuniao_2026_10_01.rttm
    transcript: transcripts/reuniao_2026_10_01.txt   # opcional, formato "SPEAKER\ttexto" por linha
    sha256: {audio: ..., rttm: ...}
    num_speakers: 4
    consent_ref: "TERMO-2026-017"
    retain_until: "2027-04-01"
```

Criptografia **não** é implementada no projeto: o `verify` só alerta se o
diretório não estiver num ponto de montagem conhecido como cifrado (best
effort, aviso, não erro). Registrar em D-021.

**H1.c — Avaliador** (`scripts/eval_diarization.py`)

```bash
python scripts/eval_diarization.py --corpus PATH --pipeline current --out base.json
python scripts/eval_diarization.py --corpus PATH --pipeline offline --out e.json
python scripts/eval_diarization.py --compare base.json e.json
```

- `--pipeline` escolhe o caminho a medir (`current` = `DiarizationProcess.diarize_file`
  como está hoje; `offline` = Frente E; `offline+words` = F; `dual` = G).
- Saída JSON por item e agregada: `der`, `confusion`, `false_alarm`,
  `missed`, `cp_wer` (se houver transcript), `coverage`, `num_speakers_ref`,
  `num_speakers_hyp`, tempo de processamento, versões de libs.
- `--compare` imprime tabela de delta por métrica e sai ≠0 se alguma métrica
  piorar além de `--max-regression` (padrão 0.01 absoluto).
- Também aceita `--corpus tests/fixtures/corpus` (sintético) — é o que o CI usa.
- **Nunca** grava áudio, texto ou nomes no JSON; só IDs e números.

**H1.d — Baseline:** rodar `--pipeline current` no corpus sintético (e no real,
se o operador tiver) e registrar no CHANGELOG. É a referência das frentes
seguintes.

**Testes**
- `cp_wer`: idêntico → 0; labels permutados → 0; um falante trocado → valor
  conhecido calculado à mão; falantes a mais/menos na hipótese.
- `corpus_real`: `init` dentro do repo falha; `verify` detecta sha256 alterado,
  consentimento ausente e prazo vencido; `purge --dry-run` não apaga. Tudo em
  `tmp_path`, com WAV sintético.
- `eval_diarization --compare`: fixture JSON com regressão → exit ≠0.

**Aceite:** AVL-01..05 `validated-ci`; baseline registrado.

---

### Frente E — Diarizador offline com pyannote (corrige ACH-02)

**Depende de:** E1, H1. **Tamanho:** M.

**Novo módulo** `src/audio/offline_diarizer.py`

```python
@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    start: float
    end: float


class DiarizationUnavailable(RuntimeError):
    """Erro acionável: dep ausente, token ausente ou termos não aceitos."""


class OfflineDiarizer:
    def __init__(self, model_id: str = settings.diarization_model,
                 device: str = "cpu", token_env: str = "HF_TOKEN"): ...

    def check_ready(self) -> None:
        """Falha cedo com DiarizationUnavailable e mensagem com o passo a
        seguir (pip install -e '.[diarization]', definir HF_TOKEN, aceitar
        termos em hf.co/<model_id>). Nunca inclui o valor do token."""

    def diarize(self, wav_path: str, *, num_speakers: int | None = None,
                min_speakers: int | None = None,
                max_speakers: int | None = None,
                exclusive: bool = False) -> list[SpeakerTurn]: ...


def make_exclusive(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
    """Uma pessoa por instante: em sobreposição, mantém o turno que começou
    por último (quem 'tomou a palavra'); corta o anterior. Função pura."""
```

Detalhes:
- Carregar com `pyannote.audio.Pipeline.from_pretrained`. Suportar as duas
  assinaturas (`token=` no pyannote ≥4, `use_auth_token=` no 3.x) por
  `inspect.signature` ou `try/except TypeError`.
- Saída ≥4 (`DiarizeOutput`): usar `.exclusive_speaker_diarization` quando
  `exclusive=True` e existir; senão `.speaker_diarization` e, se `exclusive`,
  aplicar `make_exclusive`. Saída 3.x (`Annotation`): `itertracks`.
- Rótulos normalizados para `SPEAKER_00`, `SPEAKER_01`… por ordem de primeira
  fala (estável entre execuções).
- Cache de modelo no mesmo esquema do app (`~/.cache/gravador/audio/`).
- `src/config.py`: `diarization_model` (`DIARIZATION_MODEL`, padrão
  `pyannote/speaker-diarization-3.1`), `diarization_exclusive`
  (`DIARIZATION_EXCLUSIVE`, padrão `true`). Atualizar `.env.example`.

**Integração**
- `DiarizationProcess.diarize_file` passa a delegar para `OfflineDiarizer` e
  converte para `list[dict]` (R6). diart fica só no streaming (`run`).
- `AudioManager.reprocess_with_diarization` usa o WAV **bruto** (R2): o
  `mic_path` do `DualTrackRecorder` quando existir; senão `recorded_wav`
  (documentar que este pode conter RNNoise se o filtro estava ativo).
- `scripts/transcribe_file.py`: flags `--diarize`, `--num-speakers N`,
  `--min-speakers`, `--max-speakers`, `--no-exclusive`, `--speaker-map
  map.json` (formato de `get_speaker_map`). `--diarize` chama `check_ready()`
  antes de carregar o Whisper.
- Nesta frente a atribuição ainda é por segmento do Whisper (ponto médio do
  segmento) — por palavra é a Frente F.

**Exportação (ACH-08)**
- `CaptionSegment`: campo `speaker: str | None = None` **depois** de `text`;
  `__iter__` continua com 3 valores (R6).
- `SubtitleExporter.to_srt/to_vtt(segments, speaker_names: dict[str, str] | None = None)`:
  prefixo `[Nome] ` (ou `[SPEAKER_00] ` sem mapa). VTT pode usar `<v Nome>`
  (voice tag padrão do WebVTT) — escolher um e registrar em D-019.
- `.txt` do `transcribe_file.py`: `[HH:MM:SS] Nome: texto`.

**Testes**
- `make_exclusive`: sem sobreposição → igual; sobreposição parcial; turno
  contido em outro; saída sem nenhum par sobreposto (propriedade com
  Hypothesis, que já é dep do extra `fidelity`).
- `OfflineDiarizer` com `Pipeline` mockado (Annotation fake e DiarizeOutput
  fake): normalização de rótulos, repasse de `num_speakers`, assinatura de token.
- `check_ready`: sem pyannote → mensagem cita o extra; sem `HF_TOKEN` → cita a
  variável; o valor do token nunca aparece em `str(exc)` (teste com token
  fake no ambiente).
- Exportador: SRT/VTT com e sem falante; byte-exato com o golden atual
  quando `speaker=None` (não regride).
- Real (`requires_hf_token`): `two_speakers_no_overlap.wav` produz 2 falantes;
  DER dentro do `der_policy` do manifest.

**Aceite:** DIA-04..08 `validated-ci` (mocks) e DIA-09 `skipped-no-model` ou
`validated-local`; `eval_diarization --compare base.json e.json` sem regressão
no sintético.

---

### Frente F — Atribuição por palavra (corrige ACH-03, ACH-04, ACH-05)

**Depende de:** E. **Tamanho:** M.

**Novo módulo** `src/audio/speaker_assignment.py` (puro, sem deps pesadas)

```python
@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


def assign_words(words: list[Word], turns: list[SpeakerTurn], *,
                 tolerance: float = 0.3) -> list[tuple[Word, str | None]]:
    """Falante do turno que contém o ponto médio da palavra. Se nenhum
    contém, o turno mais próximo a até `tolerance` s; senão None.
    O(n log m) com bisect sobre turnos ordenados."""


def group_segments(assigned: list[tuple[Word, str | None]], *,
                   max_gap: float = 1.0,
                   max_duration: float = 7.0) -> list[CaptionSegment]:
    """Agrupa palavras consecutivas do mesmo falante em CaptionSegment;
    quebra na troca de falante, pausa > max_gap ou duração > max_duration."""
```

**Integração offline**
- `scripts/transcribe_file.py`: com `--diarize`, `word_timestamps=True` e
  pipeline `transcribe → diarize → assign_words → group_segments → export`.
- `eval_diarization.py --pipeline offline+words`.

**Integração ao vivo** (best effort, latência do diart)
- `TranscriberProcess`: parâmetro `word_timestamps: bool` (config
  `STT_WORD_TIMESTAMPS`, padrão `true` quando diarização ativa); o resultado
  ganha `"words": [{start, end, text}]` com tempos absolutos (somar o offset
  do batch, como já é feito com os segmentos).
- `AudioManager._handle_transcript`: se `words` presente, usar
  `assign_words` contra `self._speaker_segments` e emitir
  `on_transcription(text, speaker)` **por grupo** de mesmo falante; senão,
  comportamento antigo (R6).
- Documentar que a atribuição ao vivo é provisória; a definitiva é o
  reprocessamento offline ao parar (já existe o gancho de reprocessar).

**`OverlapCounter` (ACH-05)** — sweep line: eventos (+1/−1) ordenados por
tempo, contando tempo com ≥2 falantes **distintos** ativos (contador por
falante). Mesmo API pública.

**Testes**
- `assign_words`: palavra na fronteira; palavra em gap curto (tolerância);
  gap longo → None; turnos fora de ordem na entrada; 10⁴ palavras em < 0,5 s.
- `group_segments`: troca de falante quebra segmento; `max_gap`;
  `max_duration`; texto preservado na ordem.
- Regressão do bug: lote de 7 s com dois falantes → dois grupos com rótulos
  diferentes (falhava no `_match_speaker` antigo).
- `OverlapCounter`: mesmo falante sobreposto → 0 %; dois falantes → valor
  exato; 3 falantes simultâneos não contam em dobro.

**Aceite:** ALN-01..06 `validated-ci`; `--compare e.json f.json` com
`confusion` e `cp_wer` iguais ou melhores no sintético (e no real, se houver).

---

### Frente G — Diarização por duas faixas (corrige ACH-06, ACH-07)

**Depende de:** F. **Tamanho:** M.

**Gravação**
- `_fanout_loop`: com mixer ativo, gravar **também** mic bruto e sistema
  bruto separados (o mixado continua indo para o Whisper ao vivo). Mudar a
  "decisão de produto" do comentário atual → registrar D-020.
- `DualTrackRecorder.stop()`: gravar sidecar `<prefixo>_session.json` com
  `sample_rate`, `mic_path`, `system_path`, `mic_start_monotonic`,
  `system_start_monotonic`, `offset_s = system_start - mic_start`. Sem texto.

**Processamento** — `src/audio/dual_track.py` + `transcribe_file.py --dual SESSION.json`

1. Transcrever cada faixa separadamente (palavras com tempo).
2. Faixa do **mic** → falante `LOCAL` (nome configurável:
   `LOCAL_SPEAKER_NAME`, padrão `Eu`). Se houver mais de uma pessoa na sala,
   opção `--diarize-mic` roda o `OfflineDiarizer` também nessa faixa
   (`LOCAL_00`, `LOCAL_01`…).
3. Faixa do **sistema** → `OfflineDiarizer` → `REMOTO_00`, `REMOTO_01`…
4. Alinhar tempos com `offset_s` e mesclar por `start`.
5. **Dedupe de vazamento:** sem fone, o mic capta o alto-falante. Palavra do
   mic cujo intervalo sobrepõe fala do sistema **e** cujo texto local (janela
   de ±1 s) tem similaridade de caracteres ≥ 0,8 com o do sistema é descartada.
   Limiar em config (`BLEED_SIMILARITY`), calibrado no corpus.
6. Exportar com os nomes do speaker map.

**Testes**
- Sidecar escrito e relido; offset correto com o `FakeClock` dos testes SYNC.
- Mixer ativo → três saídas (mic bruto, sistema bruto, mixado).
- Merge: duas faixas sintéticas com offset 0,25 s → ordem e tempos corretos.
- Dedupe: mesma frase nas duas faixas → fica só a do sistema; frases
  diferentes simultâneas → ficam as duas.
- DER real no cenário `two_speakers_overlap` montado como duas faixas
  (gerador novo em `gen_fidelity_fixtures.py`, mantendo `--check` determinístico).

**Aceite:** FUS-01..06 `validated-ci`; `--compare f.json g.json` mostra queda
de `confusion` no cenário de duas faixas.

---

### Frente J — Importar e transcrever arquivo de áudio/vídeo

**Objetivo de usuário:** "gravei no celular; abro o arquivo no
gravadorLegendas e recebo a transcrição separada em Participante A, B, C…".

**Depende de:** F. **Tamanho:** M.

**J.a — Pipeline de arquivo reutilizável** (`src/audio/file_pipeline.py`)

Tirar a lógica de `scripts/transcribe_file.py` para `src/` (a UI não importa
`scripts/`). O script vira um wrapper fino da mesma função.

```python
@dataclass
class FileTranscript:
    source: str
    duration_s: float
    segments: list[CaptionSegment]      # com .speaker preenchido
    speakers: dict[str, str]            # SPEAKER_00 -> "Participante A"
    diarized: bool                      # False se diarização indisponível


def transcribe_audio_file(path: str, *, num_speakers: int | None = None,
                          label_style: str = settings.speaker_label_style,
                          on_progress: Callable[[float], None] | None = None,
                          cancel: threading.Event | None = None) -> FileTranscript: ...
```

- **Formatos:** `.wav .mp3 .m4a .mp4 .ogg .opus .flac .webm` (inclui áudio de
  WhatsApp e vídeo de celular; `.mp4` usa só a faixa de áudio).
- **Decodificação:** `decode_to_wav16k(path) -> Path` com **PyAV** (`av`, já
  instalado como dependência do faster-whisper) — sem exigir `ffmpeg` no
  sistema. Saída mono 16 kHz em `tempfile`, apagada ao final (R1). O mesmo WAV
  alimenta Whisper e diarizador, para os tempos baterem.
- **Fluxo:** decodificar → `OfflineDiarizer.check_ready()` → transcrever com
  `word_timestamps=True` → diarizar (`num_speakers` se informado) →
  `assign_words` → `group_segments` → rotular.
- **Sem diarização disponível** (sem extra ou sem `HF_TOKEN`): transcreve
  mesmo assim, `diarized=False`, e a UI avisa o motivo exato (mensagem do
  `check_ready`). Nunca falha a transcrição por causa da separação de voz.
- **Progresso:** fração = fim do último segmento do Whisper / duração; a
  diarização reporta como etapa ("Separando vozes…"). `cancel` checado entre
  segmentos.

**J.b — Rótulos "Participante A, B, C"** (`src/audio/speaker_labels.py`)

```python
def friendly_labels(turns: list[SpeakerTurn], *, style: str = "letters",
                    prefix: str = "Participante") -> dict[str, str]:
    """Ordem da primeira fala: 1º a falar = A. letters: A..Z, AA, AB…;
    numbers: Participante 1, 2…; raw: SPEAKER_00."""
```

- Config: `SPEAKER_LABEL_STYLE=letters|numbers|raw` (padrão `letters`),
  `SPEAKER_LABEL_PREFIX` (padrão `Participante`). Atualizar `.env.example`.
- Os rótulos entram como **nomes padrão** no speaker map existente
  (`{sid: {name, color}}`); o usuário renomeia "Participante A" → "Juliana" no
  painel Falantes e a exportação usa o nome novo.
- CLI: `transcribe_file.py --diarize --labels letters`.

**J.c — Interface**

- Botão **"📂 Importar áudio…"** nos controles de gravação + atalho `Ctrl+O`
  (registrar em `src/ui/shortcuts.py` e na tabela de atalhos do README).
  Desabilitado enquanto grava; gravar fica desabilitado enquanto importa.
- `tkinter.filedialog.askopenfilename` com filtro "Áudio e vídeo" pelos
  formatos acima.
- Diálogo curto antes de começar: "Nº de participantes (opcional)" e
  modelo Whisper (padrão `STT_MODEL`; sugerir `small` para fala natural).
- Execução em **processo separado** (mesmo padrão `spawn` do
  `TranscriberProcess`, para não travar a UI nem deadlockar com
  torch/tkinter); status bar mostra etapa e %; botão Cancelar.
- Resultado no painel de transcrição como `[00:01:12] Participante A: texto`,
  linhas do painel Falantes criadas automaticamente, e os botões existentes
  (Copiar, Salvar .txt, Exportar .md) funcionando sobre o resultado; acrescentar
  "Exportar .srt/.vtt" se ainda não houver na UI.
- Arquivos de saída: por padrão em `settings.recording_dir` com o nome base do
  original (`audio_celular.mp3` → `audio_celular.txt/.srt/.vtt/.md`), sem
  sobrescrever sem confirmação.

**Limitações a declarar na UI/README (honestas)**
- Celular grava **uma faixa só**: a separação depende só do timbre. Vozes
  parecidas, fala sobreposta e aparelho longe dos falantes aumentam a troca
  de participante. Informar o nº de participantes ajuda.
- Rótulos A/B/C valem **por arquivo**: o "Participante A" de um arquivo não é
  a mesma pessoa do "A" de outro (identificação persistente é a Frente I).
- Tempo de processamento depende de modelo, CPU/GPU e duração; a UI mostra
  progresso, não promessa de tempo.

**Testes**
- `decode_to_wav16k` (`importorskip("av")`): gerar mp3, m4a e mp4 sintéticos
  em `tmp_path` com PyAV a partir de uma senoide → WAV mono 16 kHz, duração
  ±1 frame; arquivo corrompido → erro acionável; temporário removido.
- `friendly_labels`: ordem da primeira fala; 27º falante = `AA`; estilos
  `numbers` e `raw`; prefixo customizado.
- `transcribe_audio_file` com Whisper e diarizador mockados: segmentos com
  `speaker`; sem diarização → `diarized=False` e texto presente; `cancel`
  interrompe; `on_progress` monotônico até 1.0.
- UI (mesmo estilo de `tests/test_ui_shortcuts.py`): `Ctrl+O` chama o handler;
  importação bloqueada durante gravação; resultado popula painel Falantes.
- Real (`requires_hf_token`): `three_speakers.wav` convertido para mp3 →
  3 participantes A/B/C.

**Aceite:** IMP-01..07 `validated-ci`; teste manual registrado no CHANGELOG
com um áudio de celular do operador (sem versionar o áudio — R3).

---

### Frente H2 — Métricas no relatório de fidelidade e no CI

**Depende de:** G. **Tamanho:** P.

- `schemas/audio-fidelity-report-v1.json`: seção opcional `diarization`
  (`der`, `confusion`, `false_alarm`, `missed`, `cp_wer`, `coverage`,
  `pipeline`, `corpus`), sem quebrar reports antigos (campos opcionais;
  `schema_version` minor bump).
- `build_fidelity_report.py --diarization-json e.json` incorpora a saída do
  `eval_diarization.py`.
- `audio-fidelity.yml` (nightly/opt-in): após os testes `requires_hf_token`,
  rodar `eval_diarization.py --corpus tests/fixtures/corpus --pipeline dual`
  e anexar ao artefato. Job de PR não muda (D-005/D-010).
- README: seção "Diarização" atualizada (pyannote offline, duas faixas,
  flags do `transcribe_file.py`, limitações honestas).

**Aceite:** REL-01..03 `validated-ci`.

---

### Frente I — Voiceprints (condicional)

**Depende de:** H2 **e** de: (a) requisito explícito do dono do produto,
(b) RIPD aprovada (rodar a revisão LGPD sobre o desenho abaixo antes de
codar), (c) termo de consentimento definido. Sem os três, a frente fica
`blocked` com registro em DECISOES (D-022). **Tamanho:** M.

Desenho:
- `scripts/voiceprints.py enroll --name N --wav amostra.wav --consent-ref ID --retain-until DATA`
  extrai embedding (o modelo de embedding do próprio pipeline pyannote) a
  partir de ≥ 20 s de fala limpa.
- Armazenamento: `data/voiceprints.enc` (já gitignored por `data/`), cifrado
  com `cryptography.fernet`; chave via `keyring` do SO ou `VOICEPRINT_KEY`.
  Arquivo nunca é JSON em claro (o scan da E0 já pega o nome).
- Identificação: centróide do embedding de cada cluster da diarização vs
  voiceprints por cosseno; acima de `VOICEPRINT_THRESHOLD` (calibrar no
  corpus real; partir de 0,75) → **sugere** o nome no speaker map. Nunca
  sobrescreve um nome editado pelo usuário.
- `revoke --name N` e `purge` (retenção vencida). Log nunca contém
  embeddings.
- Testes com embeddings sintéticos (vetores fixos): cifra/decifra, chave
  errada falha, limiar, revoke, purge, sugestão não sobrescreve nome manual.

**Aceite:** VOZ-01..06 `validated-ci` + RIPD anexada ao PR.

---

## 5. Matriz rastreável

Status conforme a convenção de `docs/qualidade-audio/PLANO-IMPLEMENTACAO.md`.

| ID | Requisito | Frente | Arquivos | Tipo de teste | Status |
|---|---|---|---|---|---|
| PRIV-01 | Áudio fora de `tests/fixtures/corpus/audio` reprova o scan | E0 | `scripts/secret_scan_changed_files.py` | sintético/offline | pending |
| PRIV-02 | RTTM fora do corpus sintético reprova | E0 | idem | sintético/offline | pending |
| PRIV-03 | Caminho com `voiceprint` reprova | E0 | idem, `.gitignore` | sintético/offline | pending |
| FILA-01 | Whisper e diarizador recebem todos os chunks | E1 | `src/audio/manager.py` | integração-real-lib | pending |
| FILA-02 | Diarizador recebe áudio pré-RNNoise | E1 | idem | integração-real-lib | pending |
| AVL-01 | `cp_wer` correto e invariante a permutação | H1 | `tests/fidelity/text_metrics.py` | sintético/offline | pending |
| AVL-02 | `corpus_real init` recusa diretório no repo | H1 | `scripts/corpus_real.py` | sintético/offline | pending |
| AVL-03 | `corpus_real verify` detecta hash, consentimento e prazo | H1 | idem | sintético/offline | pending |
| AVL-04 | `eval_diarization --compare` falha em regressão | H1 | `scripts/eval_diarization.py` | sintético/offline | pending |
| AVL-05 | Baseline do pipeline atual registrado | H1 | `CHANGELOG.md` | integração-real-lib | pending |
| DIA-04 | `make_exclusive` sem sobreposição na saída | E | `src/audio/offline_diarizer.py` | sintético/offline | pending |
| DIA-05 | Rótulos normalizados e estáveis | E | idem | sintético/offline | pending |
| DIA-06 | `check_ready` acionável e sem vazar token | E | idem | sintético/offline | pending |
| DIA-07 | `diarize_file` delega ao offline mantendo contrato | E | `src/audio/diarize.py` | sintético/offline | pending |
| DIA-08 | SRT/VTT/TXT com falante; sem falante byte-exato ao atual | E | `subtitle_exporter.py`, `models.py` | sintético/offline | pending |
| DIA-09 | pyannote real em `two_speakers_no_overlap` dentro do orçamento | E | `tests/fidelity/test_diarization_der.py` | requer-modelo-hf | pending |
| ALN-01 | Palavra → falante pelo ponto médio | F | `src/audio/speaker_assignment.py` | sintético/offline | pending |
| ALN-02 | Tolerância e `None` em gap longo | F | idem | sintético/offline | pending |
| ALN-03 | Agrupamento por falante/pausa/duração | F | idem | sintético/offline | pending |
| ALN-04 | Lote com 2 falantes gera 2 rótulos (regressão ACH-03) | F | `src/audio/manager.py` | integração-real-lib | pending |
| ALN-05 | `transcribe_file --diarize` usa timestamps por palavra | F | `scripts/transcribe_file.py` | sintético/offline | pending |
| ALN-06 | `OverlapCounter` sweep line, só falantes distintos | F | `src/audio/metrics.py` | sintético/offline | pending |
| FUS-01 | Mixer ativo ainda grava faixas brutas | G | `src/audio/manager.py` | integração-real-lib | pending |
| FUS-02 | Sidecar de sessão com offset | G | `src/audio/recorder.py` | integração-real-lib | pending |
| FUS-03 | Merge de faixas com offset | G | `src/audio/dual_track.py` | sintético/offline | pending |
| FUS-04 | Dedupe de vazamento mic←alto-falante | G | idem | sintético/offline | pending |
| FUS-05 | Fixture determinística de duas faixas | G | `scripts/gen_fidelity_fixtures.py` | sintético/offline | pending |
| FUS-06 | Confusão cai no cenário de duas faixas (medido) | G | `eval_diarization.py` | requer-modelo-hf | pending |
| IMP-01 | mp3/m4a/mp4/ogg/opus/flac/webm → WAV 16 kHz mono via PyAV | J | `src/audio/file_pipeline.py` | integração-real-lib | pending |
| IMP-02 | Pipeline de arquivo compartilhado por CLI e UI | J | idem, `scripts/transcribe_file.py` | sintético/offline | pending |
| IMP-03 | Rótulos Participante A, B, C por ordem de fala | J | `src/audio/speaker_labels.py` | sintético/offline | pending |
| IMP-04 | Sem diarização disponível → transcreve e avisa | J | `src/audio/file_pipeline.py` | sintético/offline | pending |
| IMP-05 | Botão Importar + `Ctrl+O`, bloqueado durante gravação | J | `src/ui/app.py`, `recording_controls.py`, `shortcuts.py` | sintético/offline | pending |
| IMP-06 | Progresso e cancelamento sem travar a UI | J | idem | integração-real-lib | pending |
| IMP-07 | Resultado popula transcrição, painel Falantes e exportações | J | `results_panel.py`, `subtitle_exporter.py` | sintético/offline | pending |
| REL-01 | Seção `diarization` opcional no schema | H2 | `schemas/…v1.json` | sintético/offline | pending |
| REL-02 | Report incorpora `eval_diarization` | H2 | `build_fidelity_report.py` | sintético/offline | pending |
| REL-03 | Nightly publica métricas de diarização | H2 | `audio-fidelity.yml` | requer-modelo-hf | pending |
| VOZ-01..06 | Enroll, cifra, limiar, sugestão, revoke, purge | I | `scripts/voiceprints.py` | sintético/offline | blocked (D-022) |

---

## 6. Decisões a registrar (`docs/diarizacao/DECISOES.md`)

Formato igual a `docs/qualidade-audio/DECISOES.md` (Contexto / Decisão /
Alternativas / Consequências / Reverter). Numeração continua a existente.

| ID | Tema | Decisão proposta |
|---|---|---|
| D-017 | Filas | Fan-out explícito; diarizador recebe áudio bruto (pré-RNNoise). |
| D-018 | Diarizador offline | pyannote `Pipeline` para arquivo; diart só para streaming. |
| D-019 | Falante na legenda | Prefixo `[Nome]` em SRT/TXT; em VTT, `[Nome]` ou `<v Nome>` (escolher e justificar). |
| D-020 | Gravação com mixer | Mixer não suprime as faixas brutas; reverte a decisão de produto do comentário atual. |
| D-021 | Corpus real | Fora do repo, sha256 + consentimento + retenção; cifragem é do volume, não do app. |
| D-022 | Voiceprints | Bloqueado até requisito explícito + RIPD + consentimento. |
| D-023 | Avaliação | Ganho só por `eval_diarization --compare`; nenhuma estimativa. |

---

## 7. Fora de escopo (e por quê)

| Item | Motivo |
|---|---|
| Gravar a 48 kHz | Pipeline e modelos são 16 kHz; custo sem ganho (R1). |
| SepFormer/DPRNN, DOA/beamforming | Inviável em CPU e captura mono/dupla; reavaliar só com array e GPU. |
| Nemotron/Tiron/MOSS | Só depois de H1: entram como pipeline alternativo do `eval_diarization`, atrás da mesma interface `diarize(wav) -> list[SpeakerTurn]`, se o corpus real provar ganho em pt-BR. |
| Metadados de active speaker do Teams | Depende de Graph API/tenant; a Frente G cobre o híbrido. |
| CLI `agent ...` (roadmap, scaffold, schema migrate, simulate) | Duplica pytest/CI/scripts existentes; estimativa de ganho sem medição viola D-023. |
| Denoise como etapa padrão | ACH-10 / D-009. |

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| pyannote fraco em pt-BR | Medir no corpus real (H1) antes de mudar default; `DIARIZATION_MODEL` configurável. |
| CPU lenta em reuniões longas | Offline roda ao parar, em processo separado; registrar tempo no `eval_diarization`; documentar `STT_DEVICE`/GPU. |
| `torch`/pyannote quebram o job de PR | R5: imports tardios + `importorskip`; nada pesado no `ci.yml`. |
| Mudança de API do pyannote (3.x → 4.x) | Adaptador de assinatura e de saída em um único ponto (`OfflineDiarizer`), testado com mocks das duas formas. |
| Vazamento mic←alto-falante | Dedupe (FUS-04) + recomendação de fone no README. |
| Dado pessoal no repo | E0 antes de qualquer corpus real; `verify` recusa diretório no repo. |
| Diart ao vivo continua impreciso | Rótulo ao vivo é provisório; offline ao parar é a fonte de verdade. |

---

## 9. Definição de pronto (cada PR)

- [ ] `pytest tests/ -q` verde **sem** extras opcionais.
- [ ] `pytest tests/fidelity -m fidelity` verde com extra `fidelity`.
- [ ] `flake8 src/ --max-line-length=100 --extend-ignore=E501,W503,E203` limpo.
- [ ] `python scripts/gen_fidelity_fixtures.py --check` e `python scripts/fidelity_golden.py verify` verdes.
- [ ] `python scripts/secret_scan_changed_files.py` sem achados.
- [ ] Matriz da §5 atualizada; decisão registrada se houve escolha de design.
- [ ] CHANGELOG com comando executado e resultado (números colados da saída).
- [ ] A partir de E: `eval_diarization --compare` anexado à descrição do PR.
- [ ] CI do PR verde.

---

## 10. Estimativa de tamanho

| Frente | Tamanho | Observação |
|---|---|---|
| E0 | P | ~1 dia |
| E1 | P | ~1 dia; corrige bug crítico, pode sair junto com E0 |
| H1 | M | 2–4 dias; anotação do corpus real é trabalho humano à parte |
| E | M | 3–5 dias |
| F | M | 3–5 dias |
| G | M | 3–5 dias |
| J | M | 3–5 dias; entregável ao usuário logo após F |
| H2 | P | 1–2 dias |
| I | M | 3–5 dias, **após** RIPD e consentimento |

Caminho crítico sem a Frente I: ~4–5 semanas de trabalho do agente, mais o
tempo humano de anotar 3–5 reuniões em RTTM. Caminho mais curto até
"importar áudio do celular com Participante A/B/C na UI": E0 → E1 → H1 → E →
F → J (~3 semanas).
