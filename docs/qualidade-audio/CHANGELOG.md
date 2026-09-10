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
