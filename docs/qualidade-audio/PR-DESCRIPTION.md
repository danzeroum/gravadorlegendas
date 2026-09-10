# PR: Suíte de Testes de Fidelidade de Captura de Áudio

> Branch: `feat/audio-fidelity-test-suite` → `main`
> Esta descrição está pronta para uso ao abrir a PR (copiar/colar).
> Referência completa: `docs/qualidade-audio/RELATORIO-EXECUCAO.md`

---

## Contexto e objetivo de negócio

O `gravadorlegendas` é uma solução **local-first e auditável** para
registros de reuniões: captura, transcrição, diarização e exportação com
evidências mensuráveis de qualidade. Isso é particularmente valioso para
ambientes que exigem privacidade, LGPD, governança, jurídico, RH, saúde e
setor público — contextos em que "parece funcionar" não é aceitável e
qualidade precisa ser **demonstrável por cenário**.

Esta PR implementa a suíte de testes de fidelidade de captura de áudio
de ponta a ponta, ampliando (não substituindo) a base existente:
golden master, corpus determinístico, testes metamórficos,
property-based/fuzzing, contratos, budgets de performance, WER/CER
objetivos para transcrição, harness de DER para diarização, relatórios
JSON reprodutíveis e gates de CI — com rastreabilidade completa em
`docs/qualidade-audio/`.

A proposta não é prometer "transcrição perfeita" nem "prova jurídica
garantida": é qualidade mensurável por cenário, integridade e
rastreabilidade operacional, transparência sobre limitações e controle
local dos dados.

## Escopo implementado (por IDs da matriz)

| Grupo | IDs | Entrega |
|---|---|---|
| Integridade de sinal | FID-01..06 | Pico espectral ±5 Hz, RMS ±1 dB, sem clipping introduzido, downmix com energia preservada, DC < 1e-3 — todos pelo caminho REAL de conversão do backend |
| Temporização | FID-07..10 | Chunk conforme config, continuidade lógica bit a bit, formato canônico, jitter p95 (smoke 50 ms) |
| Contratos | CONF-01..04 | Protocol real dos backends, formato canônico entre tamanhos de chunk, erros explícitos, fachada retrocompatível E2E |
| Metamórficos | MET-01..05 | Ganho escala RMS linearmente; chunk_frames invariante; resample preserva duração/pico; permutação estéreo invariante; AGC com relações previsíveis |
| Fuzzing | FUZZ-01..06 | Hypothesis (25 exemplos, deadline=None): configs inválidas, device inexistente, chunks extremos, lifecycle idempotente, falha de device sem travar |
| Dual-track | SYNC-01..03 | Drift com FakeClock determinístico; duração/frames; stop mid-chunk → WAVs byte-exatos |
| Ruído | RUIDO-01..02 | SNR in/out pelo filtro REAL com gates honestos por backend; guard-rail textual (WER) com modelo real |
| Transcrição | STT-01..04 | WER/CER via jiwer com normalização documentada; categorias calibradas por medição real; modelo real opt-in; smoke legado preservado |
| Diarização | DIA-01..03 | DER real com pyannote.metrics (sem torch); RTTMs + política collar/overlap/label-mapping; diart real opt-in com HF_TOKEN por referência |
| Performance | PERF-01..02 | LatencyTracker real com relógio injetado (p95 determinístico); smoke budget 100 ms configurável (FIDELITY_P95_BUDGET_MS) |
| Golden | GOLD-01..02 | verify/freeze deliberado (--confirm-golden-regen); medições estáveis apenas; adulteração detectada (negativo) |
| Relatório | REP-01..02 | Schema versionado + gerador consolidado + 17 testes de contrato incl. negativos |
| CI | CI-01..03 | Job `fidelity` (offline, rápido, artefato JSON); workflow noturno real com skips explícitos e honest summary gate; permissions mínimas |
| Rastreabilidade | — | README/PLANO-IMPLEMENTACAO/DECISOES (D-001..D-012)/CHANGELOG/RELATORIO-EXECUCAO em `docs/qualidade-audio/` |

## Comandos e resultados (execução local, 2026-09-10 UTC)

| Comando | Resultado |
|---|---|
| `pytest tests/fidelity tests/golden tests/contracts tests/performance -q` | **197 passed, 2 skipped, 1 xfailed, 0 failed** |
| `pytest tests/test_audio_*.py …` (suíte existente, regressão) | **108 passed, 1 skipped** (= baseline) |
| `pytest tests/integration -q` | **5 passed, 36 skipped** (3 STT reais ativados pelo modelo em cache) |
| `python scripts/gen_fidelity_fixtures.py --check` | **100% regenerável byte a byte** |
| `python scripts/fidelity_golden.py verify` | **GOLDEN VERIFIED** |
| `python scripts/fidelity_golden.py freeze` (sem flag) | **RECUSADO (exit 1)** — guarda funciona |
| `python scripts/build_fidelity_report.py --output artifacts/fidelity/report.json` | **válido contra schema** (total=200) |
| `python scripts/secret_scan_changed_files.py` | **0 segredos** (sha256 de fixtures adjudicado) |
| `flake8` (arquivos novos + `src/`) | **0 violações** |

## Métricas observadas

| Métrica | Valor | Observação |
|---|---|---|
| WER clean | **0.000** | faster-whisper base CPU + espeak-ng pt-br (TTS determinístico) — NÃO representa WER em fala humana |
| WER low_volume (0.25x) | **0.167** | idem |
| WER moderate_noise (10 dB) | **0.500** | idem |
| CER clean / low_vol / noise | **0.000 / 0.083 / 0.333** | jiwer, normalização documentada |
| WER RUIDO-02 (fallback espectral) | **0.000 → 1.167** | **D-009**: filtro degrada fala a ponto de alucinação do Whisper — xfail estrito documentado |
| DER cópia exata | **0.000** | pyannote.metrics real (collar 0.0) — valida harness/métrica, não embeddings humanos |
| DER permutação consistente | **0.000** | invariância de label mapping (diarização ≠ identificação de pessoa) |
| DER confusão não-bijetiva | **0.18–0.44** | detectada |
| DER shift 500 ms / trunc 20% / merge | **0.43–0.62 / 0.21–0.56 / 0.36–0.61** | bandas calibradas por medição prévia |
| SNR fala+ruído pós-filtro | **−7.3 dB** (degradação — D-009) | fallback espectral; ruído puro atenuado −4.8 dB; gate silêncio OK |
| Drift dual-track | **erro ≤ 5 ms** vs offset simulado | FakeClock; recorder real |
| p95 por chunk (mixer+filtro) | **0.12 ms** | budget smoke 100 ms; produção via FIDELITY_P95_BUDGET_MS |
| Jitter p95 entrega | **< 50 ms** | smoke |
| Pico espectral sine_1k | **1000.0 Hz** | golden |
| DER/WER em vozes humanas | **N/A** | exige corpus consentido — lacuna declarada (README §6) |

## O que rodou em cada classificação

- **Sintético/offline**: normalização WER, metamórficos DSP, contratos de
  config, propriedades Hypothesis, golden, schema (sempre no PR CI).
- **Integração com código real (sem hardware)**: pump/conversão do
  PipewireCapture, fábrica/fachada, mixer/AGC, DualTrackRecorder,
  RNNoiseFilter, LatencyTracker, validador de settings — via device
  sintético determinístico.
- **Integração com bibliotecas de inferência reais**: faster-whisper
  base CPU (WER/CER reais), pyannote.metrics (DER real).
- **Hardware real (loopback PipeWire/WASAPI)**: **não executado** no
  ambiente de desenvolvimento — opt-in com skip explícito; testes
  existentes preservados inalterados.
- **Modelo/token HF (diart real)**: **não executado** (torch + HF_TOKEN
  ausentes) — skip com motivo preciso; harness pronto.

## Alterações em dependências e CI

- **Novo extra `[fidelity]`** (dev-only): jiwer, hypothesis, scipy,
  soundfile, PyYAML, jsonschema. Instalação mínima do produto
  **inalterada**.
- **Novo extra `[diarization-metrics]`** (opcional): pyannote.metrics —
  instalável **sem torch**.
- **`ci.yml`**: + job `fidelity` (~1–2 min; deps leves via
  `pip install -e . --no-deps`; sem hardware/token/modelo; relatório
  JSON como artefato; `permissions: contents: read`). Jobs lint/test
  existentes inalterados.
- **Novo `audio-fidelity.yml`**: dispatch manual + noturno 03:00 UTC
  para STT real (download modelo base ~145 MB), espeak-ng,
  pyannote.metrics e diart (HF_TOKEN **por referência de secret**,
  valor nunca ecoado). Honest summary gate: falha só com FALHAS reais;
  skips listados com motivo.
- **Impacto de tempo no PR**: job fidelity ~1–2 min adicional; fuzzing
  limitado (25 exemplos); total do pipeline permanece dominado pelo job
  `test` existente.

## Limitações e próximos passos

1. WER humano exige corpus consentido (infraestrutura pronta).
2. DER não valida embeddings em vozes humanas (declarado).
3. Hardware real: habilitar em runner self-hosted com PipeWire (os
   mesmos comandos do workflow noturno passam a executar de verdade).
4. diart real: configurar secret `HF_TOKEN` + aceitar termos dos modelos
   pyannote na conta.
5. **D-009 (recomendação de correção)**: fallback espectral degrada
   fala (−7.3 dB SNR; WER 0.000→1.167) — instalar RNNoise nativo
   (pyrnnoise) em produção e/ou corrigir a subtração espectral (PR
   dedicada; o xfail estrito falhará se "consertar" sem remover a marcação).
6. **D-008**: WasapiLoopbackCapture.start() sem PyAudio não propaga erro
   ao chamador — correção em PR dedicada com validação Windows.

## Confirmação de segurança

- **Nenhum segredo versionado**: secret scanning executado em todos os
  55 arquivos alterados (`scripts/secret_scan_changed_files.py`) — 0
  achados; os 20 SHA-256 dos manifests são hashes de integridade dos
  fixtures sintéticos (adjudicação formal registrada).
- **Nenhum áudio real/pessoal versionado**: fixtures 100% sintéticos,
  gerados por código com seed explícita, sem voz pessoal, reunião real
  ou dado confidencial; regeneráveis byte a byte.
- Secrets usados apenas por referência (`secrets.HF_TOKEN` em env de
  workflow); valores nunca ecoados em logs, commits ou artefatos.
- `artifacts/fidelity/` ignorado no Git — relatórios locais não são
  commitados; o CI os publica como artefatos.
- Nenhum merge, release, alteração de configuração administrativa ou
  branch existente. Nenhum teste existente enfraquecido (suíte de áudio
  = baseline idêntica: 108 passed/1 skipped).

## Referências

- **Fixes #4** — issue do bloqueio de push (D-012/D-013), resolvida pela
  reemissão do PAT com `Contents` + `Workflows` (RW); publicação
  verificada (D-016).
- Execução completa: `docs/qualidade-audio/RELATORIO-EXECUCAO.md`
- Matriz de rastreabilidade: `docs/qualidade-audio/PLANO-IMPLEMENTACAO.md`
- Decisões (D-001..D-016): `docs/qualidade-audio/DECISOES.md`
- Referência metodológica: `danzeroum/audio-suite`
