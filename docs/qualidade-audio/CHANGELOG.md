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
