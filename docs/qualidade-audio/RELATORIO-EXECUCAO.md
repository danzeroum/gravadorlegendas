# RELATÓRIO DE EXECUÇÃO — Suíte de Testes de Fidelidade de Áudio

Documento vivo. Atualizado ao final de cada fase com dados reais de
execução. Sem dados brutos ou logs crus — apenas resumo estruturado e
comandos reproduzíveis.

---

## 1. Identificação

| Campo | Valor |
|---|---|
| Branch | `feat/audio-fidelity-test-suite` |
| SHA inicial | `01497c5a448b926aea0bd78f601be17b18126c85` (main) |
| SHA final | tip da branch na abertura da PR (o commit que fecha este relatório não pode conter o próprio SHA — paradoxo de auto-referência; ver descrição da PR) |
| PR | **BLOQUEADA** — token sem Contents:Write (D-012); bundle + descrição prontos para push manual. Ver issue "Suíte de fidelidade: push da branch bloqueado por permissão do token" |
| Data da execução | 2026-09-10 (UTC) |

## 2. Ambiente relevante

| Componente | Valor |
|---|---|
| SO | Linux x86_64 (kernel 5.10.134), contêiner sem servidor de áudio |
| Python | 3.12.14 |
| CPU | 2 vCPU (sem GPU) |
| numpy | 2.1.3 |
| scipy | 1.14.1 |
| soundfile | 0.13.1 (libsndfile) |
| pytest | 9.0.2 |
| hypothesis | 6.168.0 |
| jiwer | instalado (extra `[fidelity]`) |
| structlog | 26.1.0 |
| pyannote.metrics | instalado (extra `[diarization-metrics]`, **sem torch**) |
| faster-whisper | 1.2.1 + modelo `base` em cache (~/.cache/gravador/audio/whisper) — instalado para evidência real local |
| espeak-ng | /usr/bin/espeak-ng (TTS determinístico) |
| PipeWire / pw-record / pactl | **ausente** no ambiente do agente |
| PyAudio / WASAPI | **ausente** (Linux) |
| diart / pyannote.audio / HF_TOKEN | **ausentes** (árvore torch + token por aceitar termos) |

> Implicação: validação local cobre caminhos sintéticos/offline,
> integração com código real do produto e integração com bibliotecas
> reais de inferência (faster-whisper, pyannote.metrics). Hardware
> real (loopback PipeWire/WASAPI) e diart real ficam opt-in com skip
> explícito — nunca simulados como sucesso.

## 3. Baseline inicial (antes de qualquer alteração)

| Comando | Resultado | Observação |
|---|---|---|
| `pytest tests/test_audio_*.py tests/test_capture.py tests/test_mixer.py tests/test_noise_*.py tests/test_recorder.py -q` | 108 passed, 1 skipped | Suíte de áudio existente saudável |
| `pytest tests/integration/ -q` | 2 passed, 39 skipped | Skips esperados: sem PipeWire/hardware |
| `pytest tests/ -q` | 7 erros de coleção | **Preexistente e fora do escopo**: módulos UI (`customtkinter`, `openai`, `transformers`) não instaláveis no ambiente do agente. O CI existente instala `requirements.txt` completo, onde não ocorrem. Nenhum problema de áudio na baseline. |

## 4. Comandos realmente executados (por fase — resumo)

| Fase | Comando | Resultado |
|---|---|---|
| 0 | baseline acima | registrada |
| 1 | `pytest tests/test_audio_backends.py tests/test_mixer.py -q` | 34 passed (markers/strict ok) |
| 2 | `python scripts/gen_fidelity_fixtures.py` + `--check` | 10 WAVs (1588 KB) + 4 RTTMs; **100% regenerável byte a byte** |
| 3 | `pytest tests/fidelity/ -q` | 33 passed |
| 4 | `pytest tests/fidelity/ -q` | 85 passed (após 3 correções nos próprios testes) |
| 5 | `pytest tests/fidelity/test_dual_track_sync.py tests/fidelity/test_noise_suppression_quality.py -q` | 16 passed, 1 skipped (faster-whisper) |
| 5 | `python scripts/measure_noise_baseline.py` | baseline SNR do filtro (D-009) |
| 6 | `python scripts/measure_wer_baseline.py` (base) | WER real calibrado por categoria |
| 6 | `pytest tests/fidelity/ -q` | 127 passed, 1 xfailed |
| 7 | `python scripts/measure_der_baseline.py` | DER real calibrado |
| 7 | `pytest tests/fidelity/test_diarization_der.py -q` | 33 passed, 1 skipped |
| 8 | `pytest tests/golden/ tests/contracts/ -q` | 26 passed |
| 8 | `python scripts/fidelity_golden.py verify` / `freeze` (sem flag) | VERIFIED / **RECUSADO exit 1** |
| 8 | `python scripts/build_fidelity_report.py --output artifacts/fidelity/report.json` | relatório válido |
| 9 | `pytest tests/fidelity tests/golden tests/contracts tests/performance -q` | 197 passed, 2 skipped, 1 xfailed |
| Final | `python scripts/secret_scan_changed_files.py` | **0 segredos** (sha256 de fixtures adjudicado) |

## 5. Execução final consolidada

| Suíte | Comando | Resultado |
|---|---|---|
| Fidelidade offline completa | `pytest tests/fidelity tests/golden tests/contracts tests/performance -q` | **197 passed, 2 skipped, 1 xfailed, 0 failed** |
| Unitária de áudio existente (regressão) | `pytest tests/test_audio_*.py ... -q` | **108 passed, 1 skipped** (idêntica à baseline — sem regressão) |
| Integração (com modelo base instalado) | `pytest tests/integration -q` | **5 passed, 36 skipped** (vs 2/39 da baseline: 3 testes STT reais ativados pelo modelo em cache, incl. lifecycle do TranscriberProcess) |
| Corpus determinístico | `python scripts/gen_fidelity_fixtures.py --check` | **100% regenerável** |
| Golden master | `python scripts/fidelity_golden.py verify` | **VERIFIED** |
| Relatório JSON | `python scripts/build_fidelity_report.py` | **válido contra schema** (total=200, golden=verified) |

**Skips (todos com motivo rastreável):**
1. `TestDia03RealDiarization::test_diarization_process_contract_on_pseudo_speech` — diart não instalado (árvore torch); job noturno com HF_TOKEN.
2. `TestPerf01StageBudgets::test_vad_stage_optin` — silero-vad não instalado (torch); job noturno/self-hosted.

**XFail (falha conhecida registrada, nunca sucesso fingido):**
1. `TestRuido02TextualQuality::test_filter_does_not_worsen_clean_transcription_wer` — **D-009**: fallback espectral degrada fala (WER 0.000→1.167, alucinação do Whisper); guard-rail T5.2 exigível apenas com RNNoise nativo.

## 6. Métricas observadas (reais, com classificação)

| Métrica | Valor | Como foi medida | Classificação |
|---|---|---|---|
| WER clean | **0.000** | faster-whisper base CPU + espeak-ng pt-br (TTS determinístico), `scripts/measure_wer_baseline.py` | real-lib (sem hardware) |
| WER low_volume (0.25x) | **0.167** | idem | real-lib |
| WER moderate_noise (10 dB) | **0.500** | idem + ruído gaussiano seed 99 | real-lib |
| CER clean / low_vol / noise | **0.000 / 0.083 / 0.333** | jiwer com normalização documentada | real-lib |
| WER RUIDO-02 (fallback espectral) | **0.000 → 1.167** (degradação) | filtro real + whisper base | real-lib — evidência do D-009 (xfail) |
| DER cópia exata | **0.000** | pyannote.metrics real (collar 0.0) sobre RTTMs do corpus | real-lib |
| DER permutação consistente | **0.000** | idem (invariância de label mapping — diarização ≠ identificação) | real-lib |
| DER confusão não-bijetiva | **0.18–0.44** | idem | real-lib |
| DER shift 500 ms | **0.43–0.62** | idem (banda [0.30, 0.70] do manifesto) | real-lib |
| DER truncamento 20% | **0.21–0.56** | idem | real-lib |
| DER merge 1 falante | **0.36–0.61** | idem | real-lib |
| DER hipótese vazia | **1.000** | idem | real-lib |
| SNR fixture moderate_noise | **10.0 dB** (alvo exato) | dsp_utils.snr_db sobre corpus | sintético |
| SNR ruído puro pós-filtro | **+4.8 dB** de atenuação | RNNoiseFilter real (fallback espectral) | real-lib |
| SNR fala+ruído pós-filtro | **−7.3 dB** (degradação — D-009) | idem | real-lib |
| SNR sinal limpo pós-filtro | **3.19 dB** (degradação — D-009) | idem | real-lib |
| Pico espectral sine_1k | **1000.0 Hz** (±5 Hz) | FFT com interpolação sub-bin via pump real | real-lib |
| RMS sine_1k | **−9.03 dBFS** (±1 dB) | idem | real-lib |
| Rail fraction fixture clipado | **0.0428** (vs ~1e-5 limpo) | detector de flat-topping | sintético |
| Drift dual-track (FakeClock) | **erro ≤ 5 ms** vs offset simulado | DualTrackRecorder real | real-lib |
| p95 por chunk (mixer+filtro) | **0.12 ms** (budget smoke 100 ms) | monotônico por chunk, 200 chunks | real-lib |
| Jitter p95 de entrega (FID-10) | **< 50 ms** (smoke) | TimingQueue no loop real | real-lib |
| p95 LatencyTracker (FakeClock) | **exato** (0.5 s simulado) | tracker real com relógio injetado | determinístico |
| DER/WER humanos (vozes reais) | **N/A** | exige corpus consentido — lacuna declarada | não medido |

## 7. Testes reais vs mock/sintéticos (classificação honesta)

| Categoria | O que cobre | Exemplos |
|---|---|---|
| **Sintético/offline** | Normalização WER, metamórficos DSP, contratos de config, propriedades Hypothesis, golden, schema | STT-01/02, MET-03/04, FUZZ-01..06, GOLD-*, REP-* |
| **Integração com código real (sem hardware)** | Pump/conversão do PipewireCapture real, fábrica/fachada reais, mixer/AGC real, DualTrackRecorder real, RNNoiseFilter real, LatencyTracker real, validador de settings real | FID-01..04, 06..10, CONF-*, MET-01/02/05, SYNC-*, RUIDO-01 |
| **Integração com bibliotecas de inferência reais** | faster-whisper base CPU (WER/CER reais sobre TTS determinístico), pyannote.metrics real (DER) | STT-03, RUIDO-02 (xfail), DIA-01 |
| **Hardware/loopback real** | PipeWire/WASAPI — **não executado neste ambiente**; opt-in com skip explícito; preservados sem alteração | testes `requires_pipewire`/`requires_wasapi` de tests/integration/ |
| **Modelo/token HF (opt-in)** | diart real — **não executado** (torch + HF_TOKEN ausentes); skip com motivo preciso | DIA-03 |
| **Indisponível no runner atual** | Job `fidelity` do CI e workflow noturno — versionados, aguardam execução no PR | CI-01..03 |

## 8. Problemas encontrados e correções

| # | Problema | Tipo | Resolução |
|---|---|---|---|
| 1 | 7 erros de coleção de testes UI na baseline (deps pesadas ausentes no agente) | preexistente | Documentado; fora do escopo de áudio; CI existente não é afetado |
| 2 | `clipped_fraction` com threshold fixo 0.999 não detectava clipping em nível 0.25 | bug do teste (minha métrica) | Semântica alterada para rail-hit no pico observado; calibrado |
| 3 | Comparação bit a bit exigia replicar truncamento do pump (não `rint`) | bug do teste | Replicada aritmética exata float32×32767→int16 |
| 4 | Entrada não-múltipla de chunk gerava falha de continuidade | bug do teste | Entrada aparada para múltiplo exato (comportamento do pump documentado) |
| 5 | `dsp.db` (10·log10) usado para razão de RMS (20·log10) | bug do teste | Comparação linear com tolerância ±6% |
| 6 | FakeSettings sem campos exigidos pelo validador real | bug do teste | SimpleNamespace com todos os campos + filtro de valores válidos |
| 7 | **Fallback espectral degrada SNR de fala em 7.3 dB** (e sinal limpo a 3.2 dB) | **achado de produto (D-009)** | Tripwire 12 dB no manifesto + xfail estrito no RUIDO-02 + recomendação de RNNoise nativo; correção fora do escopo (documentada) |
| 8 | **WasapiLoopbackCapture.start() sem PyAudio não propaga erro ao chamador** | **achado de produto (D-008)** | Documentado como teste de registro; correção exige Windows real (PR futura) |
| 9 | Threshold DER ingênuo do manifesto (0.12 p/ shift) divergia das medições (0.43–0.62) | calibração | Bandas medidas substituíram valores estimados |
| 10 | Senoide pura tem 1/8 de amostras no pico (dwell natural ≠ clipping) | calibração | Teste de sanity corrigido para o fixture certo |
| 11 | JUnit representa xfail via `type="pytest.xfail"`, não mensagem | bug do parser do relatório | Parser corrigido; xfailed=1 no relatório final |

## 9. Limitações remanescentes

1. **WER em fala humana não é medido**: TTS espeak é voz robótica — os
   valores calibrados representam consistência do pipeline, não WER de
   reunião real. Corpus consentido humano é lacuna aberta (README §6).
2. **DER não valida embeddings em vozes humanas**: pseudo-fala valida
   harness, timeline e métrica (declarado nos testes e no manifesto).
3. **Hardware real não executado no ambiente do agente**: loopback
   PipeWire/WASAPI permanece opt-in; `requires_pipewire`/`requires_wasapi`
   fazem skip rastreável.
4. **diart real não executado**: exige torch + HF_TOKEN com termos aceitos
   (intervenção humana). Skip com motivo preciso; harness pronto.
5. **RNNoise nativo não validado**: pyrnnoise não instalável no agente
   (binding C). O gate de qualidade de supressão real (≥1 dB SNR) só
   roda onde instalado — documentado.
6. **Fallback espectral (D-009) permanece com degradação conhecida**:
   monitorada por tripwire; correção recomendada em PR dedicada.
7. **CI-01..03**: workflows versionados e sintaticamente válidos; a
   validação de execução plena acontece no próprio PR (resultado será
   visível nos checks e no artefato `audio-fidelity-report`).
8. **Idempotência do corpus entre versões de libs**: WAVs são
   determinísticos por seed; a estabilidade entre versões de
   numpy/libsndfile é mitigada por golden de propriedades físicas com
   tolerâncias (não hash de bytes como único gate).

## 10. Referências

- Matriz: `docs/qualidade-audio/PLANO-IMPLEMENTACAO.md`
- Decisões: `docs/qualidade-audio/DECISOES.md` (D-001..D-011)
- Changelog fase a fase: `docs/qualidade-audio/CHANGELOG.md`
- Manifesto do corpus (budgets/limiares calibrados):
  `tests/fixtures/corpus/manifest.yaml`
- Golden congelado: `tests/golden/manifest.yaml`
- Schema do relatório: `schemas/audio-fidelity-report-v1.json`
- Relatório local (não versionado): `artifacts/fidelity/report.json`
- Referência metodológica: repositório `danzeroum/audio-suite`
- Secret scanning: `python scripts/secret_scan_changed_files.py`
  (0 achados; sha256 de fixtures adjudicado como integridade)
