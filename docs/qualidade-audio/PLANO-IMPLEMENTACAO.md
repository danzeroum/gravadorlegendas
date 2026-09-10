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

**Convenção de tipo de teste:**

| Tipo | Descrição |
|---|---|
| `sintético/offline` | Executa apenas com sinais gerados em código, sem bibliotecas de áudio real. |
| `integração-real-lib` | Exercita bibliotecas reais do produto (numpy, soundfile, mixer, recorder) sem hardware. |
| `hardware/loopback` | Exige dispositivo de áudio real ou sessão PipeWire/WASAPI (opt-in). |
| `requer-modelo-hf` | Exige modelo Whisper/diart baixado ou token Hugging Face (opt-in). |
| `indisponivel-runner` | Não executável no runner atual de CI hospedado; documentado. |

## Matriz

| ID | Requisito | Arquivos | Tipo de teste | Status | Evidência |
|---|---|---|---|---|---|
| FID-01 | Pico espectral de senoide 1 kHz dentro de ±5 Hz no caminho digital | `tests/fidelity/test_capture_signal_integrity.py` | sintético/offline | implemented | — |
| FID-02 | RMS em ±1 dB contra referência em caminho digital controlado | `tests/fidelity/test_capture_signal_integrity.py` | sintético/offline | implemented | — |
| FID-03 | Amostras normalizadas em [-1, 1] (float) / [-32768, 32767] (int16), sem clipping introduzido | `tests/fidelity/test_capture_signal_integrity.py` | sintético/offline | implemented | — |
| FID-04 | Contagem de frames com tolerância ≤ 1 chunk | `tests/fidelity/test_capture_timing.py` | sintético/offline | implemented | — |
| FID-05 | Downmix mono/estéreo preservando energia dentro de tolerância | `tests/fidelity/test_capture_signal_integrity.py` | sintético/offline | implemented | — |
| FID-06 | DC offset abaixo de limiar documentado | `tests/fidelity/test_capture_signal_integrity.py` | sintético/offline | implemented | — |
| FID-07 | Tamanho do chunk conforme `AudioCaptureConfig.chunk_frames` | `tests/fidelity/test_capture_timing.py` | sintético/offline | implemented | — |
| FID-08 | Ausência de gaps/overlaps lógicos no contador de frames | `tests/fidelity/test_capture_timing.py` | sintético/offline | implemented | — |
| FID-09 | Sample rate e formato canônico (pcm_s16le mono) corretos | `tests/fidelity/test_capture_timing.py` | sintético/offline | implemented | — |
| FID-10 | Jitter p95 de entrega de chunks medido e abaixo de budget | `tests/fidelity/test_capture_timing.py` | sintético/offline | implemented | — |
| CONF-01 | Backends reais aderem ao Protocol `AudioCaptureBackend` | `tests/fidelity/test_backend_conformance.py` | integração-real-lib | implemented | — |
| CONF-02 | Chunks publicados em formato canônico (bytes PCM s16le) | `tests/fidelity/test_backend_conformance.py` | integração-real-lib | implemented | — |
| CONF-03 | Erros explícitos: `start` sem pw-record levanta RuntimeError | `tests/fidelity/test_backend_conformance.py` | integração-real-lib | implemented | — |
| CONF-04 | Fachada `AudioCapture` retrocompatível (API preservada) | `tests/fidelity/test_backend_conformance.py` | integração-real-lib | implemented | — |
| MET-01 | Ganho de entrada escala RMS de modo previsível | `tests/fidelity/test_capture_metamorphic.py` | sintético/offline | implemented | — |
| MET-02 | `chunk_frames` diferente não altera materialmente energia/duração | `tests/fidelity/test_capture_metamorphic.py` | sintético/offline | implemented | — |
| MET-03 | Resampling preserva duração temporal | `tests/fidelity/test_capture_metamorphic.py` | sintético/offline | implemented | — |
| MET-04 | Permutação de canais estéreo não quebra contratos | `tests/fidelity/test_capture_metamorphic.py` | sintético/offline | implemented | — |
| MET-05 | Ganho de mixagem AGC: normalização pós-AGC previsível | `tests/fidelity/test_capture_metamorphic.py` | integração-real-lib | implemented | — |
| FUZZ-01 | Configurações inválidas (sample rate) → erro explícito/gracioso | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| FUZZ-02 | Canais inválidos → erro explícito/gracioso | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| FUZZ-03 | Dispositivo inexistente → falha sem exceção mascarada | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| FUZZ-04 | Chunks extremos (0, 1, ímpar, gigante) não corrompem pipeline | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| FUZZ-05 | Duplo `start()` idempotente; `stop()` sem `start()` seguro | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| FUZZ-06 | Falha/interrupção de dispositivo tratada sem travamento | `tests/fidelity/test_capture_fuzz.py` | sintético/offline | implemented | — |
| SYNC-01 | Drift entre trilhas mic/sistema em cenário controlado ≤ budget | `tests/fidelity/test_dual_track_sync.py` | integração-real-lib | implemented | — |
| SYNC-02 | Igualdade de duração/frames dentro de tolerância | `tests/fidelity/test_dual_track_sync.py` | integração-real-lib | implemented | — |
| SYNC-03 | `stop()` no meio de chunk produz WAVs válidos e recuperáveis | `tests/fidelity/test_dual_track_sync.py` | integração-real-lib | implemented | — |
| RUIDO-01 | SNR entrada/saída medido para sinal + ruído sintético | `tests/fidelity/test_noise_suppression_quality.py` | integração-real-lib | implemented | — |
| RUIDO-02 | Filtro não degrada qualidade textual (STT real opcional opt-in) | `tests/fidelity/test_noise_suppression_quality.py` | requer-modelo-hf | implemented | — |
| STT-01 | WER/CER calculado com jiwer e normalização documentada | `tests/fidelity/test_transcription_wer.py` | sintético/offline | implemented | — |
| STT-02 | Baseline WER por categoria no manifesto do corpus | `tests/fixtures/corpus/manifest.yaml` | sintético/offline | implemented | — |
| STT-03 | Teste com modelo real (faster-whisper) opt-in com skip explícito | `tests/fidelity/test_transcription_wer.py` | requer-modelo-hf | implemented | — |
| STT-04 | Smoke test antigo de termos preservado | `tests/integration/test_e2e_stt_quality_real.py` (inalterado) | hardware/loopback | implemented | — |
| DIA-01 | DER com pyannote.metrics quando extra opcional instalado | `tests/fidelity/test_diarization_der.py` | sintético/offline | implemented | — |
| DIA-02 | RTTM de referência do corpus + política de collar/overlap | `tests/fixtures/corpus/rttm/` | sintético/offline | implemented | — |
| DIA-03 | Diart/pyannote real marcado `requires_hf_token`, skip sem token | `tests/fidelity/test_diarization_der.py` | requer-modelo-hf | implemented | — |
| PERF-01 | Budget de latência p95 injetável/determinístico (smoke) | `tests/performance/test_capture_latency_budget.py` | sintético/offline | implemented | — |
| PERF-02 | Reuso de `LatencyTracker` para p95 | `tests/performance/test_capture_latency_budget.py` | sintético/offline | implemented | — |
| GOLD-01 | Golden master verify/freeze com ação explícita | `scripts/fidelity_golden.py`, `tests/golden/` | sintético/offline | implemented | — |
| GOLD-02 | Golden guarda apenas medições estáveis (sem wall-clock) | `tests/golden/manifest.yaml` | sintético/offline | implemented | — |
| REP-01 | Relatório JSON consolidado com schema versionado | `scripts/build_fidelity_report.py`, `schemas/audio-fidelity-report-v1.json` | sintético/offline | implemented | — |
| REP-02 | Schema validado em teste de contrato | `tests/contracts/test_audio_fidelity_report_schema.py` | sintético/offline | implemented | — |
| CI-01 | CI de PR: lint + suíte offline sem hardware/token/modelo | `.github/workflows/ci.yml` | indisponivel-runner | implemented | — |
| CI-02 | Job real/opt-in noturno com skips explícitos | `.github/workflows/audio-fidelity.yml` | indisponivel-runner | implemented | — |
| CI-03 | Upload de relatório JSON como artefato de CI | `.github/workflows/ci.yml` | indisponivel-runner | implemented | — |

> Nota: os status acima refletem o estado **inicial** (Fase 0). O status final,
> com evidências reais de execução, é atualizado conforme cada fase é concluída
> em commits subsequentes e consolidado ao final em RELATORIO-EXECUCAO.md.
