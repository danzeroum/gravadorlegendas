# Qualidade de Áudio — Suíte de Testes de Fidelidade de Captura

> Diretório de documentação e rastreabilidade da suíte de testes de
> fidelidade de áudio do `gravadorlegendas`. Referência metodológica:
> repositório `danzeroum/audio-suite` (golden master, corpus determinístico,
> testes metamórficos, property-based testing, fuzzing, contratos, budgets
> de performance, evidências reprodutíveis e gates de CI).

## 1. Objetivo e escopo

Validar com **rigor mensurável** que o produto captura áudio de reuniões de
forma fiel, preserva sincronismo, é robusto contra configurações adversas e
não regride transcrição ou diarização. A suíte complementa — não substitui —
os testes existentes (`tests/` unitários e `tests/integration/` reais).

Cobertura por responsabilidade:

| Responsabilidade | Diretório | IDs da matriz |
|---|---|---|
| Integridade de sinal | `tests/fidelity/test_capture_signal_integrity.py` | FID-01..FID-06 |
| Temporização de captura | `tests/fidelity/test_capture_timing.py` | FID-07..FID-10 |
| Contratos de backend | `tests/fidelity/test_backend_conformance.py` | CONF-01..CONF-04 |
| Testes metamórficos | `tests/fidelity/test_capture_metamorphic.py` | MET-01..MET-05 |
| Fuzzing/robustez | `tests/fidelity/test_capture_fuzz.py` | FUZZ-01..FUZZ-06 |
| Dual-track e sincronismo | `tests/fidelity/test_dual_track_sync.py` | SYNC-01..SYNC-03 |
| Supressão de ruído | `tests/fidelity/test_noise_suppression_quality.py` | RUIDO-01..RUIDO-02 |
| Transcrição (WER/CER) | `tests/fidelity/test_transcription_wer.py` | STT-01..STT-04 |
| Diarização (DER) | `tests/fidelity/test_diarization_der.py` | DIA-01..DIA-03 |
| Performance (p95) | `tests/performance/test_capture_latency_budget.py` | PERF-01..PERF-02 |
| Golden master | `tests/golden/` + `scripts/fidelity_golden.py` | GOLD-01..GOLD-02 |
| Relatório JSON | `scripts/build_fidelity_report.py` + `schemas/` | REP-01..REP-02 |

Matriz completa com status/evidência: `PLANO-IMPLEMENTACAO.md`.

## 2. Instalação de dependências

```bash
# Suíte completa de fidelidade (dev + métricas de áudio)
pip install -e ".[dev,audio,fidelity]"

# Opcional — métricas DER offline (pyannote.metrics + torch, pesado)
pip install -e ".[diarization-metrics]"

# Opcional — diarização real com diart/pyannote.audio (requer token HF)
pip install -e ".[diarization]"
```

O extra `[fidelity]` adiciona: `jiwer` (WER/CER), `hypothesis`
(property-based/fuzz), `scipy` (análise espectral), `PyYAML` (manifestos)
e `jsonschema` (validação de contrato do relatório). Não altera a
instalação mínima do produto.

## 3. O que roda onde

| Contexto | O que roda | Como |
|---|---|---|
| **Local (qualquer máquina)** | Suíte offline completa: unit + fidelity + golden + contracts + performance smoke | `pytest -m "fidelity or golden or performance" -q` |
| **Local (Linux com PipeWire)** | + testes reais de loopback PipeWire | `pytest -m "requires_pipewire" -q` |
| **Local (Windows com WASAPI)** | + testes reais de loopback WASAPI | `pytest -m "requires_wasapi" -q` |
| **PR (GitHub Actions)** | lint + suíte offline + golden verify + relatório JSON como artefato | automático em `.github/workflows/ci.yml` |
| **Noturno/manual (real)** | testes `real_audio`, PipeWire, STT com modelo, diarização com token | workflow `.github/workflows/audio-fidelity.yml` (dispatch/schedule; jobs reais fazem **skip explícito** quando o recurso não existe — nunca simulam sucesso) |

## 4. Comandos de execução

```bash
# Corpus determinístico (regenera fixtures + manifestos — idempotente)
python scripts/gen_fidelity_fixtures.py

# Suíte de fidelidade completa (offline, sem hardware/token/modelo)
pytest tests/fidelity tests/golden tests/contracts tests/performance -q

# Por marcador
pytest -m fidelity -q               # integridade/contratos/metamórficos/WER/DER
pytest -m golden -q                 # golden master verify
pytest -m performance -q            # budgets de latência (smoke)
pytest -m fuzz -q                   # fuzzing (examples limitados no PR)
pytest -m "requires_hf_token" -q    # só com token HF no ambiente

# Golden master
python scripts/fidelity_golden.py verify                     # verifica contra baseline
python scripts/fidelity_golden.py freeze --confirm-golden-regen  # regenera (ação deliberada!)

# Relatório JSON consolidado
python scripts/build_fidelity_report.py --output artifacts/fidelity/report.json
```

## 5. Métricas e limiares

| Métrica | O que mede | Onde | Limiar (fonte) |
|---|---|---|---|
| Pico espectral | Frequência dominante de senoide 1 kHz | FID-01 | ±5 Hz (manifesto) |
| RMS (dBFS) | Energia vs referência digital | FID-02 | ±1 dB (manifesto) |
| Clipping | % de amostras em saturação | FID-03 | 0% introduzido |
| DC offset | Média != 0 | FID-06 | < 0.001 |
| Contagem de frames | Frames entregues vs esperado | FID-04 | ±1 chunk |
| Jitter p95 | Variabilidade de entrega | FID-10 | budget smoke generoso (PERF) |
| Drift dual-track | Diferença de samples entre trilhas | SYNC-01/02 | calibrado no manifesto |
| SNR | Sinal/ruído antes/depois do filtro | RUIDO-01 | calibrado no manifesto |
| WER | Word Error Rate de transcrição | STT-01 | por categoria no manifesto do corpus |
| CER | Character Error Rate | STT-01 | por categoria no manifesto do corpus |
| DER | Diarization Error Rate | DIA-01 | por cenário no manifesto (collar 0.0) |
| Latência p95 | Intervalo entre batches transcritos | PERF-01 | smoke no PR; production no noturno |

Todos os limiares vivem em `tests/fixtures/corpus/manifest.yaml` e
`tests/golden/manifest.yaml` — **não hard-coded em testes**. Valores foram
calibrados com baseline local executado antes de serem fixados (ver
DECISOES.md e calibrações no manifesto).

## 6. Limitações por plataforma/hardware

- **Sem PipeWire/pw-record** (CI hospedado, contêineres): testes
  `requires_pipewire` fazem skip explícito. O caminho de conversão
  f32→s16le do PipeWire é coberto offline com streams sintéticos.
- **Windows/WASAPI**: exige PyAudio + Windows; testes `requires_wasapi`
  fazem skip fora desse ambiente.
- **Sem GPU**: testes com modelo real usam CPU com modelo `tiny`/`base` —
  marcados `requires_stt_model`/`requires_hf_token`.
- **WER em fala humana**: a suíte atual mede WER/CER sobre pseudo-fala
  sintética determinística. Isso valida a **infraestrutura de métrica e
  regressão relativa**, não o WER absoluto esperado em voz humana
  (documentado em DECISOES.md D-003). Corpus consentido é lacuna aberta.
- **DER em vozes humanas**: sinais pseudo-falados validam contrato,
  timeline, integração e métricas — **não** a qualidade de
  embeddings/diarização em vozes humanas.

## 7. Política de atualização do golden master

1. `python scripts/fidelity_golden.py verify` roda no CI de PR. Falha de
   golden **bloqueia** o PR.
2. Para atualizar deliberadamente (após mudança intencional de
   comportamento): `python scripts/fidelity_golden.py freeze
   --confirm-golden-regen` **e** justificativa no corpo do commit/PR
   usando a convenção `golden-regen` no título ou seção dedicada.
3. O golden guarda **somente medições estáveis**: hash de fixture,
   duração, frame count, RMS, pico espectral e tolerâncias. Wall-clock,
   jitter absoluto e caminhos de máquina **nunca** são congelados.
4. Revisores devem tratar diff de golden sem justificativa como red flag.

## 8. Política de corpus e privacidade

- Fixtures são 100% sintéticos, gerados por código com seed explícita
  (`tests/fixtures/signal_generators.py`), licenciáveis sob a mesma
  licença do repositório, sem voz pessoal, reunião real ou dado
  confidencial.
- Regeneração: `python scripts/gen_fidelity_fixtures.py` (idempotente —
  mesmo seed ⇒ mesmos bytes, sujeito apenas a diferenças de
  formato WAV entre versões de libsndfile, mitigado por guardar
  propriedades físicas no golden em vez de hash de bytes como gate único).
- `artifacts/fidelity/` é ignorado por `.gitignore`: relatórios de
  execução local não são commitados; o CI os publica como artefatos.

## 9. Como interpretar o relatório JSON

Gerado por `python scripts/build_fidelity_report.py`, validado contra
`schemas/audio-fidelity-report-v1.json`:

```
{
  "schema_version": "1",              # versão do contrato do relatório
  "generated_at": "2026-09-10T...",   # timestamp UTC ISO-8601
  "commit_sha": "abc123...",          # commit quando disponível
  "environment": { ... },             # SO/Python/libs — SEM dados sensíveis
  "summary": { "total": N, "passed": N, "failed": N, "skipped": N },
  "results": [                        # um item por teste/cenário
    {
      "test_id": "FID-01",
      "test_name": "...",
      "status": "passed|failed|skipped",
      "category": "sintetico|integracao-real-lib|hardware|modelo|indisponivel",
      "metrics": { "wer": 0.12, ... },
      "thresholds": { ... },
      "skip_reason": "..."            # apenas quando skipped
    }
  ],
  "limitations": [ ... ]              # limitações declaradas da execução
}
```

- `status=skipped` **não é sucesso**: cada skip traz `skip_reason`
  rastreável.
- `category` diferencia explicitamente teste sintético/offline, integração
  com bibliotecas reais, hardware/loopback real, dependência de
  modelo/token e indisponível no runner atual.
- Métricas ausentes aparecem como `null` com explicação em
  `limitations` — nunca omitidas silenciosamente.

## 10. Rastreabilidade

| Documento | Papel |
|---|---|
| `PLANO-IMPLEMENTACAO.md` | Matriz ID → requisito → arquivos → status → evidência |
| `DECISOES.md` | Decisões arquiteturais numeradas com alternativas e reversão |
| `CHANGELOG.md` | Registro incremental fase a fase (UTC) |
| `RELATORIO-EXECUCAO.md` | Execuções reais: comandos, métricas, problemas, limitações |
