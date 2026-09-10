# PLANO DE IMPLEMENTAÇÃO — Suíte de Testes de Fidelidade de Áudio

Matriz rastreável de requisitos da suíte de fidelidade de captura de áudio
do `gravadorlegendas`. Cada requisito tem ID estável, arquivos, tipo de teste,
status e evidência.

**Convenção de status:**

| Status | Significado |
|---|---|
| `implemented` | Código existe, mas ainda não foi executado ou a execução não foi registrada. |
| `validated-local` | Executado e aprovado no ambiente local do agente (Linux, sem hardware de áudio). |
| `validated-ci` | Executado e aprovado no CI de pull request. |
| `blocked` | Inviável no ambiente atual, com causa registrada em DECISOES.md. |
| `skipped-no-hardware` | Exige hardware/loopback/sessão PipeWire real — opt-in, skip explícito. |
| `skipped-no-model` | Exige modelo/token — opt-in, skip com motivo preciso. |
| `preserved` | Teste legado preservado sem alteração. |

**Convenção de tipo de teste:**

| Tipo | Descrição |
|---|---|
| `sintético/offline` | Executa apenas com sinais gerados em código, sem bibliotecas de áudio real. |
| `integração-real-lib` | Exercita bibliotecas/código real do produto (numpy/scipy/soundfile/mixer/recorder/backends) sem hardware. |
| `hardware/loopback` | Exige dispositivo de áudio real ou sessão PipeWire/WASAPI (opt-in). |
| `requer-modelo-hf` | Exige modelo Whisper/diart baixado ou token Hugging Face (opt-in). |
| `indisponivel-runner` | Não executável no runner atual de CI hospedado; documentado. |

## Matriz — STATUS FINAL (2026-09-10)

| ID | Requisito | Arquivos | Tipo de teste | Status | Evidência |
|---|---|---|---|---|---|
| FID-01 | Pico espectral de senoide 1 kHz dentro de ±5 Hz no caminho real de conversão | `tests/fidelity/test_capture_signal_integrity.py` | integração-real-lib | **validated-local** | Passa pelo pump REAL do PipewireCapture; detector negativo (1030 Hz) valida não-tautologia; golden: pico=1000.0 Hz |
| FID-02 | RMS em ±1 dB contra referência analítica | idem | integração-real-lib | **validated-local** | 3 níveis de amplitude; golden: RMS=−9.03 dBFS; detector de queda 3 dB |
| FID-03 | Amostras normalizadas, sem clipping introduzido | idem | integração-real-lib | **validated-local** | rail fraction < 0.001 no caminho; fixture clipado detectado (0.0428) |
| FID-04 | Contagem de frames com tolerância ≤ 1 chunk | `tests/fidelity/test_capture_timing.py` | integração-real-lib | **validated-local** | múltiplo exato → 100 chunks exatos; cauda → floor ±1; proporcionalidade |
| FID-05 | Downmix mono/estéreo preservando energia | `test_capture_signal_integrity.py` | sintético/offline | **validated-local** | duplicated/half (−3.01 dB) /antifase; contrato --channels 1 no cmd real |
| FID-06 | DC offset abaixo de 1e-3 | idem | integração-real-lib | **validated-local** | DC ≈ 0 no pump; adversarial 0.05 detectado; silêncio = 0 exato |
| FID-07 | Tamanho do chunk conforme `AudioCaptureConfig.chunk_frames` | `test_capture_timing.py` | integração-real-lib | **validated-local** | 160/480/960 → bytes exatos (chunk×2) |
| FID-08 | Ausência de gaps/overlaps lógicos | idem | integração-real-lib | **validated-local** | concatenação bit a bit == entrada; sem duplicação de objetos |
| FID-09 | Sample rate e formato canônico (pcm_s16le mono) | idem | sintético/offline | **validated-local** | `--rate` no cmd real (8k/16k/44.1k); s16le par; AudioChunk defaults |
| FID-10 | Jitter p95 medido (smoke budget 50 ms) | idem | integração-real-lib | **validated-local** | TimingQueue com timestamps monotônicos; p95 medido < budget |
| CONF-01 | Backends reais aderem ao Protocol | `tests/fidelity/test_backend_conformance.py` | integração-real-lib | **validated-local** | isinstance nos 2 backends reais + fábrica; superfície de métodos |
| CONF-02 | Chunks em formato canônico | idem | integração-real-lib | **validated-local** | equivalência de conteúdo entre 3 tamanhos de chunk |
| CONF-03 | Erros explícitos (sem pw-record / backend inválido) | idem | integração-real-lib | **validated-local** | RuntimeError actionable; AudioBackendError explícito |
| CONF-04 | Fachada retrocompatível | idem | integração-real-lib | **validated-local** | E2E fachada→fábrica→backend→chunks; chaves legadas; D-008 documentado |
| MET-01 | Ganho escala RMS previsivelmente | `tests/fidelity/test_capture_metamorphic.py` | integração-real-lib | **validated-local** | linear ±6% em 4 ganhos; saturação viola relação (negativo) |
| MET-02 | chunk_frames invariante (energia/duração/conteúdo) | idem | integração-real-lib | **validated-local** | bit a bit idêntico entre 160/480/960 |
| MET-03 | Resampling preserva duração/pico | idem | sintético/offline | **validated-local** | 44.1k→16k ±1 sample; roundtrip; pico 1 kHz sobrevive |
| MET-04 | Permutação de canais não quebra contratos | idem | sintético/offline | **validated-local** | downmix invariante; RMS por canal preservado; antifase detectável |
| MET-05 | AGC do mixer com relações previsíveis | idem | integração-real-lib | **validated-local** | limitador invariante a amplitude; linear sem AGC; passthrough bit a bit |
| FUZZ-01 | Sample rate inválido → erro/pass-through gracioso | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | **validated-local** | Hypothesis 25 exemplos; validador real acusa; cmd reflete valor |
| FUZZ-02 | Canais inválidos → fachada sempre mono | idem | sintético/offline | **validated-local** | propriedade channels==1; validador real acusa |
| FUZZ-03 | Dispositivo inexistente → EOF gracioso | idem | sintético/offline | **validated-local** | 0 chunks, sem travar; factory com device não-numérico → erro explícito |
| FUZZ-04 | Chunks extremos (0/1/ímpar/gigante) | idem | sintético/offline | **validated-local** | PCM válido; mixer com bytes arbitrários nunca quebra |
| FUZZ-05 | Duplo start / stop sem start / stop duplo | idem | sintético/offline | **validated-local** | 1 Popen apenas (idempotência); N stops seguros |
| FUZZ-06 | Falha de dispositivo sem travamento | idem | sintético/offline | **validated-local** | spawn quebrado → thread termina, is_running False; morte mid-stream preserva chunks |
| SYNC-01 | Drift entre trilhas controlado | `tests/fidelity/test_dual_track_sync.py` | integração-real-lib | **validated-local** | FakeClock: offset 0.25 s medido com erro ≤ 5 ms; gap de samples exato |
| SYNC-02 | Igualdade de duração/frames | idem | integração-real-lib | **validated-local** | duração = samples/rate ± budget; trilha mais longa |
| SYNC-03 | stop() mid-chunk → WAVs válidos | idem | integração-real-lib | **validated-local** | headers corretos; conteúdo byte-exato; chunk ímpar gracioso |
| RUIDO-01 | SNR entrada/saída com gates honestos por backend | `tests/fidelity/test_noise_suppression_quality.py` | integração-real-lib | **validated-local** | p95/frame 0.12 ms; gate silêncio OK; ruído puro −4.8 dB; D-009 tripwire |
| RUIDO-02 | Filtro não degrada qualidade textual | idem | requer-modelo-hf | **validated-local (xfail D-009)** | Evidência real: WER 0.000→1.167 (alucinação) no fallback espectral; xfail estrito documentado |
| STT-01 | WER/CER com normalização documentada | `tests/fidelity/test_transcription_wer.py` | sintético/offline | **validated-local** | 22 testes incl. propriedades Hypothesis (idempotência, WER self=0) |
| STT-02 | Baseline WER por categoria no manifesto | `tests/fixtures/corpus/manifest.yaml` | sintético/offline | **validated-local** | categorias calibradas com medição real; teste de coerência |
| STT-03 | WER real com faster-whisper (opt-in) | `test_transcription_wer.py` | requer-modelo-hf | **validated-local** | **Real**: clean 0.000, low_volume 0.167, noise 0.500 (base CPU + espeak) |
| STT-04 | Smoke test legado preservado | `tests/integration/test_e2e_stt_quality_real.py` | hardware/loopback | **preserved** | Arquivo inalterado; contrato de não-regressão testado |
| DIA-01 | DER com pyannote.metrics real | `tests/fidelity/test_diarization_der.py` | integração-real-lib | **validated-local** | **Real** (sem torch): cópia 0.0; permutação 0.0; confusão 0.18–0.44; shift/trunc/merge nas bandas |
| DIA-02 | RTTM de referência + política collar/overlap | `tests/fixtures/corpus/rttm/` | sintético/offline | **validated-local** | 4 RTTMs íntegros e consistentes com o manifesto |
| DIA-03 | diart real marcado requires_hf_token | `test_diarization_der.py` | requer-modelo-hf | **skipped-no-model** | Skip com motivo preciso (diart ausente — árvore torch); harness pronto |
| PERF-01 | Budget p95 injetável/determinístico | `tests/performance/test_capture_latency_budget.py` | sintético/offline | **validated-local** | FakeClock → p95 exato; smoke real 0.12 ms < 100 ms; FIDELITY_P95_BUDGET_MS |
| PERF-02 | Reuso do LatencyTracker | idem | sintético/offline | **validated-local** | Tracker real: gaps conhecidos, pico na cauda, histórico limitado |
| GOLD-01 | Golden verify/freeze com ação deliberada | `scripts/fidelity_golden.py`, `tests/golden/` | sintético/offline | **validated-local** | verify OK; freeze sem flag RECUSADO; adulteração detectada (negativo) |
| GOLD-02 | Golden guarda apenas medições estáveis | `tests/golden/manifest.yaml` | sintético/offline | **validated-local** | Contrato testado contra campos proibidos (wall-clock/jitter/path) |
| REP-01 | Relatório JSON com schema versionado | `scripts/build_fidelity_report.py`, `schemas/audio-fidelity-report-v1.json` | sintético/offline | **validated-local** | Relatório real gerado e validado (200 testes) |
| REP-02 | Schema validado em teste de contrato | `tests/contracts/test_audio_fidelity_report_schema.py` | sintético/offline | **validated-local** | 17 testes incl. negativos (schema rejeita inválidos) |
| CI-01 | CI de PR offline (sem hardware/token/modelo) | `.github/workflows/ci.yml` | indisponivel-runner | **implemented** | Job `fidelity` (deps leves, corpus check, golden verify, relatório); validação plena ocorre ao abrir o PR |
| CI-02 | Job real/opt-in noturno com skips explícitos | `.github/workflows/audio-fidelity.yml` | indisponivel-runner | **implemented** | dispatch + cron 03:00 UTC; HF_TOKEN por referência; honest summary gate |
| CI-03 | Upload de relatório JSON como artefato | ambos os workflows | indisponivel-runner | **implemented** | actions/upload-artifact@v4 com if-no-files-found: error |

> **Nota de honestidade sobre os statuses:**
> - `validated-local` = executado no ambiente do agente (Linux sem
>   hardware de áudio, com faster-whisper base + espeak-ng +
>   pyannote.metrics instalados localmente para evidência real).
> - `implemented` (CI-01..03) = workflows versionados e sintaticamente
>   válidos; a validação de execução plena acontece no próprio PR — os
>   resultados são registrados em RELATORIO-EXECUCAO.md quando disponíveis.
> - Nenhum teste com hardware real foi executado neste ambiente: os de
>   hardware permanecem opt-in (`requires_pipewire`/`requires_wasapi`)
>   com skip explícito.
