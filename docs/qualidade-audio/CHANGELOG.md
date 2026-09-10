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
