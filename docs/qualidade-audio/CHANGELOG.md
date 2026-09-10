# CHANGELOG — Suíte de Testes de Fidelidade de Áudio

Formato: cada entrada tem data/hora UTC, descrição objetiva, arquivos
envolvidos, testes executados e resultado.

---

## 2026-09-10 06:53 UTC — Fase 0: descoberta e baseline

**Descrição:** Branch `feat/audio-fidelity-test-suite` criada a partir de
`main` (SHA inicial `01497c5a448b926aea0bd78f601be17b18126c85`). Leitura
completa de `src/audio/` (capture, backends pipewire/wasapi, factory,
mixer, recorder, vad, transcribe, diarize, manager, metrics),
`src/platform/types.py`, `tests/conftest.py`, `tests/integration/`,
`pyproject.toml`, `requirements*.txt`, `.github/workflows/ci.yml` e
`.gitignore`. Baseline de testes executada e registrada.

**Arquivos envolvidos:** somente leitura + criação de
`docs/qualidade-audio/` (este CHANGELOG, PLANO-IMPLEMENTACAO.md,
DECISOES.md, README.md, RELATORIO-EXECUCAO.md).

**Testes executados (baseline, sem alterações de código):**

| Comando | Resultado |
|---|---|
| `pytest tests/test_audio_*.py tests/test_capture.py tests/test_mixer.py tests/test_noise_*.py tests/test_recorder.py -q` | **108 passed, 1 skipped** |
| `pytest tests/integration/ -q` | **2 passed, 39 skipped** (sem PipeWire/hardware — esperado) |
| `pytest tests/ -q` (coleção completa) | **7 erros de coleção** preexistentes: `customtkinter`, `openai`, `transformers` ausentes no ambiente do agente — fora do escopo de áudio; não corrigidos (decisão documentada em RELATORIO-EXECUCAO.md) |

**Resultado:** Fase 0 concluída sem alterações em código de produção.

---

## 2026-09-10 07:10 UTC — Fase 3: integridade de sinal e temporização

**Descrição:** Testes FID-01..FID-10 implementados. Harness
`tests/fidelity/fake_device.py` permite exercitar o loop de captura REAL do
`PipewireCapture` (thread + conversão f32→s16le + fila + terminação de
subprocesso) com device sintético, sem hardware — classificado como
integração com código real (offline). 2 correções de teste durante o
desenvolvimento: (1) comparação bit a bit precisa replicar a aritmética
exata do pump (float32×32767 com truncamento, não round); (2) continuidade
lógica exige entrada múltipla do chunk (pump descarta fragmento final —
comportamento documentado do produto).

**Arquivos envolvidos:**
- `tests/fidelity/fake_device.py` (novo)
- `tests/fidelity/conftest.py` (novo)
- `tests/fidelity/test_capture_signal_integrity.py` (novo — FID-01..06)
- `tests/fidelity/test_capture_timing.py` (novo — FID-04, 07..10)
- `tests/fidelity/dsp_utils.py` (correção: rail-hit clipping fraction)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity/ -q` | **33 passed** |
| `flake8 tests/fidelity/ tests/fixtures/ scripts/gen_fidelity_fixtures.py` | **0 violações** |

**Resultado:** FID-01..FID-10 com status `validated-local`.

---

## 2026-09-10 07:22 UTC — Fase 4: contratos, metamórficos e fuzzing

**Descrição:** CONF-01..04, MET-01..05 e FUZZ-01..06 implementados.
Hypothesis configurado com max_examples=25 e deadline=None (estabilidade de
CI — nenhuma propriedade depende de temporização real). Correções durante o
desenvolvimento: razão de RMS em escala linear (bug do próprio teste: 10·log10
vs 20·log10), FakeSettings com todos os campos do validador real, filtro de
canais válidos na estratégia. Achado documentado (D-008):
WasapiLoopbackCapture.start() sem PyAudio não propaga erro ao chamador.

**Arquivos envolvidos:**
- `tests/fidelity/test_backend_conformance.py` (novo — CONF-01..04 + D-008)
- `tests/fidelity/test_capture_metamorphic.py` (novo — MET-01..05)
- `tests/fidelity/test_capture_fuzz.py` (novo — FUZZ-01..06)
- `docs/qualidade-audio/DECISOES.md` (D-008)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity/ -q` | **85 passed** |
| `pytest tests/test_audio_backends.py tests/test_mixer.py tests/test_recorder.py tests/test_audio_manager.py -q` | **60 passed** (sem regressão) |
| `flake8 tests/fidelity/ tests/fixtures/ scripts/` | **0 violações** |

**Resultado:** CONF/MET/FUZZ com status `validated-local`.

---

## 2026-09-10 07:30 UTC — Fase 5: dual-track e supressão de ruído

**Descrição:** SYNC-01..03 e RUIDO-01..02 implementados. Drift dual-track
testado com FakeClock injetado (determinismo sem sleeps). **Achado
importante (D-009)**: baseline medido localmente mostra que o fallback
espectral do RNNoiseFilter DEGRADA o SNR de fala+ruído em ~7.3 dB e o sinal
limpo cai a ~3.2 dB — o gate de silêncio e a atenução de ruído puro (−4.8 dB)
funcionam. Budgets calibrados a partir dessas medições (tripwire de 12 dB),
nunca impostos sem medição prévia. pyrnnoise não instalável no agente —
caminho RNNoise real fica opt-in com skip explícito.

**Arquivos envolvidos:**
- `tests/fidelity/test_dual_track_sync.py` (novo — SYNC-01..03)
- `tests/fidelity/test_noise_suppression_quality.py` (novo — RUIDO-01..02)
- `tests/fidelity/text_metrics.py` (novo — utilitário WER/CER compartilhado)
- `scripts/measure_noise_baseline.py` (novo — calibração de budgets)
- `scripts/gen_fidelity_fixtures.py` (budgets no manifesto)
- `docs/qualidade-audio/DECISOES.md` (D-009)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity/test_dual_track_sync.py tests/fidelity/test_noise_suppression_quality.py -q` | **16 passed, 1 skipped** (faster-whisper ausente — motivo preciso) |
| `python scripts/measure_noise_baseline.py` | baseline SNR registrado (D-009) |

**Resultado:** SYNC/RUIDO com status `validated-local` (RUIDO-02:
`skipped-no-model` no agente, infraestrutura pronta).

---

## 2026-09-10 07:45 UTC — Fase 6: WER/CER com jiwer + modelo real validado

**Descrição:** STT-01..04 implementados. **Validação real executada
localmente**: faster-whisper `base` (CPU) instalado no ambiente do agente +
modelo em cache (~/.cache/gravador) + espeak-ng disponível → WER/CER reais
medidos sobre TTS determinístico. Thresholds por categoria calibrados por
medição prévia (scripts/measure_wer_baseline.py) e registrados no manifesto.
**Evidência adicional do D-009**: RUIDO-02 executado com modelo real — o
fallback espectral degrada WER de 0.000 para 1.167 (Whisper alucina sobre
áudio corrompido: "e a gente vai no canal no Facebook"). Tratado como
xfail estrito documentado — nunca como sucesso.

**Medições reais (faster-whisper base, espeak-ng pt-br -s 90):**

| Categoria | WER medido | CER medido | Limiar (manifesto) |
|---|---|---|---|
| clean | 0.000 | 0.000 | 0.20 / 0.15 |
| low_volume (0.25x) | 0.167 | 0.083 | 0.40 / 0.30 |
| moderate_noise (10 dB) | 0.500 | 0.333 | 0.70 / 0.50 |

**Arquivos envolvidos:**
- `tests/fidelity/test_transcription_wer.py` (novo — STT-01..04)
- `tests/fidelity/text_metrics.py` (normalização documentada + wer/cer)
- `scripts/measure_wer_baseline.py` (novo — calibração)
- `scripts/gen_fidelity_fixtures.py` (wer_policy calibrada no manifesto)
- `tests/fidelity/test_noise_suppression_quality.py` (RUIDO-02: xfail D-009)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity/ -q` | **127 passed, 1 xfailed** |
| `flake8 tests/fidelity/ scripts/` | **0 violações** |

**Resultado:** STT-01/02 `validated-local`; STT-03 `validated-local` com
modelo real (será `skipped-no-model` no PR CI, rodando no noturno); STT-04
preservado.

---

## 2026-09-10 07:55 UTC — Fase 7: DER com pyannote.metrics real

**Descrição:** DIA-01..03 implementados. **pyannote.metrics instalado e
validado localmente SEM torch** — DER real computado sobre os RTTMs do
corpus. Bandas calibradas por medição prévia
(scripts/measure_der_baseline.py). **Achado metodológico documentado**:
permutação consistente de labels → DER 0 (optimal label mapping do
pyannote) — diarização é invariante a rebatimento consistente porque
atribui IDs locais, não identidade de pessoa; confusão não-bijetiva
(segmento rebatido para falante existente) é detectada (DER 0.18–0.44).
Threshold ingênuo do manifesto (0.12 para shift) corrigido pelas bandas
medidas. DIA-03 (diart real) marcado requires_hf_token, skip com motivo
preciso (diart não instalado — árvore pesada).

**Medições DER reais (pyannote.metrics, collar 0.0):**

| Transformação | DER medido (4 cenários) | Banda no manifesto |
|---|---|---|
| cópia exata | 0.000 | 0.0 |
| permutação consistente | 0.000 | 0.0 |
| confusão não-bijetiva | 0.18–0.44 | > 0.10 |
| shift global 500 ms | 0.43–0.62 | [0.30, 0.70] |
| truncamento 20% | 0.21–0.56 | [0.15, 0.65] |
| merge em 1 falante | 0.36–0.61 | [0.30, 0.65] |
| hipótese vazia | 1.000 | 1.0 |

**Arquivos envolvidos:**
- `tests/fidelity/test_diarization_der.py` (novo — DIA-01..03)
- `scripts/measure_der_baseline.py` (novo — calibração)
- `scripts/gen_fidelity_fixtures.py` (der_policy com bandas medidas)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity/test_diarization_der.py -q` | **33 passed, 1 skipped** (diart real — motivo preciso) |
| `flake8 tests/fidelity/ scripts/` | **0 violações** |

**Resultado:** DIA-01/02 `validated-local` (pyannote.metrics real); DIA-03
`skipped-no-model` com harness pronto.

---

## 2026-09-10 08:05 UTC — Fase 8: golden master e relatório JSON

**Descrição:** GOLD-01..02 e REP-01..02 implementados. Golden master
congelado com medições estáveis apenas (sha256, samples, duração, RMS
dBFS, pico espectral, DC offset, clipping — nunca wall-clock/jitter).
`freeze` recusa sem `--confirm-golden-regen` (testado como contrato).
`verify` detecta adulteração (teste negativo: RMS +1 dB é pego). Achado
menor documentado: senoide pura tem 1/8 das amostras no pico (dwell
natural, não clipping) — detector de rail-hit calibrado no teste. Schema
versionado `schemas/audio-fidelity-report-v1.json` com if-then exigindo
skip_reason não-vazio para skips. Relatório real gerado e validado.

**Relatório real da execução local (artefato não versionado):**
- total=188, passed=186, skipped=1 (DIA-03: diart ausente — motivo preciso),
  xfailed=1 (RUIDO-02: D-009), failed=0, golden=verified
- metrics_summary: sine_peak=1000.0 Hz, sine_rms=-9.03 dBFS,
  clipped_rail=0.0428, SNR fixture=10.0 dB; WER/CER/DER humanos=null
  (limitação declarada — dependem de modelo/token)

**Arquivos envolvidos:**
- `scripts/fidelity_golden.py` (novo — verify/freeze com guarda)
- `tests/golden/manifest.yaml` (novo — baseline congelada, 10 cenários)
- `tests/golden/test_capture_golden_master.py` (novo — GOLD-01..02)
- `schemas/audio-fidelity-report-v1.json` (novo — contrato do relatório)
- `scripts/build_fidelity_report.py` (novo — gerador + validação)
- `tests/contracts/test_audio_fidelity_report_schema.py` (novo — REP-01..02)
- `.gitignore` (+ artifacts/fidelity/)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/golden/ tests/contracts/ -q` | **26 passed** |
| `python scripts/fidelity_golden.py verify` | **GOLDEN VERIFIED** |
| `python scripts/fidelity_golden.py freeze` (sem flag) | **RECUSADO (exit 1)** — guarda funciona |
| `python scripts/build_fidelity_report.py --output artifacts/fidelity/report.json` | **relatório válido** (188 testes) |
| `flake8 scripts/ tests/golden/ tests/contracts/` | **0 violações** |

**Resultado:** GOLD/REP com status `validated-local`.

---

## 2026-09-10 08:15 UTC — Fase 9: performance e CI

**Descrição:** PERF-01..02 e CI-01..03 implementados. Latência p95
determinística via FakeClock injetado no `LatencyTracker` REAL do produto
(gaps conhecidos ⇒ p95 exato, zero flakiness) + smoke budget real por
chunk (mixer + filtro: p95 medido 0.12 ms, budget generoso 100 ms,
configurável para produção via `FIDELITY_P95_BUDGET_MS` no job
noturno). CI de PR ganha job `fidelity` (~1-2 min): deps leves sem
torch (`pip install -e . --no-deps`), corpus regenerável, golden verify,
suíte offline completa e relatório JSON como artefato. Workflow separado
`audio-fidelity.yml` (dispatch + noturno 03:00 UTC) para STT real
(modelo base), espeak-ng, pyannote.metrics e diart com HF_TOKEN por
referência de secret. Gate de resumo honesto: job falha somente com
FALHAS reais — skips são listados com motivo, nunca mascarados.

**Arquivos envolvidos:**
- `tests/performance/test_capture_latency_budget.py` (novo — PERF-01..02)
- `tests/conftest.py` (fixtures de corpus compartilhadas)
- `.github/workflows/ci.yml` (job `fidelity` + permissions mínimas)
- `.github/workflows/audio-fidelity.yml` (novo — real/noturno)

**Testes executados:**

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity tests/golden tests/contracts tests/performance -q` | **197 passed, 2 skipped, 1 xfailed** |
| `pytest tests/test_audio_*.py ...` (regressão) | **73 passed** |
| `flake8` (meus arquivos + src/) | **0 violações** |
| YAML workflows | **válido em ambos** |

**Resultado:** PERF `validated-local`; CI-01..03 `implemented` (validação
plena ocorre na execução do PR — documentado na matriz).

---

## 2026-09-10 08:30 UTC — Fechamento: relatório final, matriz final e PR

**Descrição:** Suíte completa executada e consolidada. Matriz
PLANO-IMPLEMENTACAO.md atualizada com status final fiel (validated-local
com evidências, implemented para CI aguardando execução no PR,
skipped-no-model onde aplicável). RELATORIO-EXECUCAO.md finalizado com
SHA, ambiente, métricas reais, classificação honesta real/mock, problemas
e limitações. Secret scanning executado em todos os 55 arquivos
alterados: **0 segredos** (20 SHA-256 de fixtures adjudicados como
integridade deliberada). Decisões D-010/D-011 registradas.

**Resultado final consolidado:**

| Suíte | Resultado |
|---|---|
| Fidelidade offline (fidelity+golden+contracts+performance) | **197 passed, 2 skipped, 1 xfailed, 0 failed** |
| Unitária de áudio existente (regressão) | **108 passed, 1 skipped** (= baseline) |
| Integração (modelo base instalado) | **5 passed, 36 skipped** (3 STT reais ativados) |
| Corpus determinístico | **100% regenerável byte a byte** |
| Golden master | **VERIFIED**; freeze sem flag RECUSADO |
| Relatório JSON | **válido contra schema** (200 testes, golden verified) |
| Secret scanning | **0 segredos** (adjudicação formal de falsos positivos) |
| flake8 (arquivos novos + src/) | **0 violações** |

---

## 2026-09-10 08:40 UTC — Bloqueio registrado: push impossível com o token fornecido

**Descrição:** Token GitHub autentica (identidade OK) mas tem Contents
apenas Read — `git push` e Git Data API retornam 403. Sem `Contents:Write`
não há como criar a branch remota nem abrir a PR (head inexistente).
Decisão D-012: não contornar limites de permissão do token. Mitigação
entregue: branch local completa verificada, git bundle + patches para
push manual, descrição de PR pronta (PR-DESCRIPTION.md) e issue GitHub
documentando o bloqueio com passos exatos.

**Resultado:** Todos os requisitos da definição de pronto cumpridos
exceto a abertura da PR em si — bloqueada por permissão do token, não
por implementação. Evidências e caminho de conclusão manual registrados.

---

## 2026-09-10 08:50 UTC — Entrega final consolidada

**Descrição:** Issue #4 criada documentando o bloqueio de permissão com
passos exatos de conclusão manual. Bundle git + série de 13 patches +
descrição de PR prontos. Suíte final validada: 197 passed, 2 skipped,
1 xfailed; regressão zero; golden verified; secret scanning limpo.

**Resultado:** Definição de pronto cumprida integralmente exceto a
abertura física da PR — bloqueada por Contents read-only do token
(D-012), com caminho de conclusão manual documentado e entregue.

---

## 2026-09-10 10:10 UTC — Segundo bloqueio de push registrado (D-013: permissão Workflows)

**Descrição:** Token reemitido com `Contents: Read and write` (D-012
resolvido): o `git push` autenticou e alcançou o GitHub, mas foi
rejeitado pela proteção de workflows — PAT sem permissão **Workflows**
não pode criar/alterar arquivos em `.github/workflows/` (esta entrega
versiona `ci.yml` + `audio-fidelity.yml`, requisitos CI-01..03).
Mensagem completa registrada em D-013; issue #4 atualizada com
comentário interino de diagnóstico. Nenhum contorno tentado (proteção
legítima; mesmo princípio de D-012). Ação do mantenedor: acrescentar
Workflows → Read and write ao token.

**Resultado:** Push/PR aguardam ação do mantenedor. Branch local íntegra
(14 commits, HEAD `1405169`). O tempo de espera foi convertido em
hardening pré-push (D-014/D-015) — a branch nasce CI-ready no primeiro
run do PR.

---

## 2026-09-10 10:25 UTC — Hardening de CI: coleção graciosa sem deps opcionais (D-014)

**Descrição:** O job `test` do CI instala apenas `requirements.txt`
(numpy/PyYAML transitivos; scipy/soundfile/hypothesis/jiwer/jsonschema
ausentes). Sem guarda, as suítes fidelity/golden/contracts/performance
falhariam na coleta e em runtime. Evidência red→green em ambiente
simulado do job `test`: antes — 4 erros de coleta (hypothesis×2,
soundfile×2) + 3 falhas de runtime (scipy lazy em MET-03); depois — 0
erros, suítes fora da coleção com nota no header do pytest. Guarda
central em `tests/conftest.py` (`collect_ignore_glob` +
`pytest_report_header`); `yaml` tornado lazy no conftest raiz.

**Resultado:** Job `test` permanece dono da suíte do produto; job
`fidelity` é o dono único das suítes de fidelidade. Suíte local completa
revalidada pós-mudança (ambiente reconstruído nas versões do
congelamento): **197 passed, 2 skipped, 1 xfailed** — idêntica ao
documentado; regressão de áudio **108/1** idêntica à baseline; flake8 0
violações.

---

## 2026-09-10 10:32 UTC — Hardening de CI: versões pinadas no job fidelity (D-015)

**Descrição:** `gen_fidelity_fixtures.py --check` compara bytes
regenerados vs versionados; streams de `default_rng` e ULP de `sin` são
estáveis apenas dentro das mesmas versões de libs. O job `fidelity`
agora instala exatamente as versões do congelamento do corpus
(numpy==2.1.3, scipy==1.14.1, soundfile==0.13.1) + `mkdir -p
artifacts/fidelity` antes do `--junitxml`. Golden verify permanece
robusto a versões (tolerâncias); apenas o --check exige ambiente
idêntico — e agora o tem.

**Resultado:** O runner do PR reproduz o ambiente de calibração local por
completo; o --check vale como gate de reprodutibilidade byte a byte sem
falso-positivo por drift de versão. Corpus revalidado: 100% regenerável;
GOLDEN VERIFIED; secret scanning 0 achados. Branch agora CI-ready com 16
commits — aguardando apenas a permissão Workflows (D-013) para o push.

---

## 2026-09-10 15:07 UTC — Desbloqueio e push da branch (D-016)

**Descrição:** Mantenedor reemitiu o PAT com **Workflows → Read and
write** (requisito pendente de D-013). Push executado com protocolo de
segurança preservado (token apenas em env de comando; URL one-shot; não
persistido em arquivo/config; saídas redigidas por regex). A ref remota
`feat/audio-fidelity-test-suite` foi criada com os 17 commits, incluindo
a alteração versionada em `.github/workflows/` aceita pelo GitHub.

**Verificação pós-push:**

| Verificação | Resultado |
|---|---|
| SHA HEAD local vs remoto | `ef4ed53` — idêntico |
| Tree hash local vs remoto | `97a3e3f` — idêntico (byte-exato) |
| API compare vs `main` | 17 ahead / 0 behind |
| `python scripts/secret_scan_changed_files.py` | **0 segredos** (57 arquivos) |

**Arquivos envolvidos:** `docs/qualidade-audio/RELATORIO-EXECUCAO.md`
(adendo §11), `docs/qualidade-audio/DECISOES.md` (D-016),
`docs/qualidade-audio/PR-DESCRIPTION.md` (Fixes #4; D-001..D-016),
este CHANGELOG.

**Resultado:** Bloqueio D-012/D-013 encerrado sem contorno e com
rastreabilidade completa. Sequência final liberada: PR → revisão
Copilot → issue #4 → CI do PR → adendo §12.

---

## 2026-09-10 15:15 UTC — CI da PR #5 verde; fechamento da entrega (§12)

**Descrição:** O workflow CI executou na PR #5 (run `34493659033`,
evento `pull_request`, head `572d226`) com conclusão `success`:

- `lint`: success.
- `test`: **272 passed, 40 skipped, 0 failed** — guarda D-014 confirmada
  no runner real (header do pytest declara as suítes de fidelidade fora
  da coleção e o job `fidelity` como dono delas).
- `fidelity`: **161 passed, 6 skipped, 0 failed, 0 xfailed (total 167)
  em 6,67 s** — corpus 100% regenerável e GOLDEN VERIFIED reproduzidos
  no runner; 6 skips com motivo preciso (pyannote 1, espeak-ng 4,
  silero-vad 1); artefato `audio-fidelity-report` (11,4 KB) publicado.
- Números divergentes do local (197/2/1) por design: coleção condicional
  e skips honestos no ambiente do PR; noturno cobre o restante.

Copilot review solicitado 2× via API (201 aceito; bot não engaja —
requer habilitação do recurso nas configurações do repo pelo
mantenedor). Issue #4 encerrada como concluída com comentário final.

**Arquivos envolvidos:** `docs/qualidade-audio/RELATORIO-EXECUCAO.md`
(adendo §12), este CHANGELOG.

**Resultado:** PR #5 completa: 18 commits, CI verde nos três jobs,
artefato publicado, issue de bloqueio encerrada, trilha de auditoria
D-001..D-016 íntegra. Merge a critério do mantenedor.
