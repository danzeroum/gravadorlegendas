# DECISÕES — Suíte de Testes de Fidelidade de Áudio

Registro de decisões arquiteturais curtas, datadas e numeradas. Cada decisão
tem Contexto, Decisão, Alternativas, Consequências e como reverter.

---

## D-001 — Métrica de qualidade de transcrição: WER/CER via jiwer

**Data:** 2026-09-10 (UTC)

**Contexto:** O teste de qualidade STT existente
(`tests/integration/test_e2e_stt_quality_real.py`) valida apenas
presença/contagem de termos-chave da frase de referência. Isso é um smoke
test útil (integração de pipeline), mas não é uma métrica objetiva de
regressão de transcrição: uma transcrição com 40% de palavras erradas pode
passar se os 2 termos-chave sobreviverem.

**Decisão:** Adotar WER (Word Error Rate) como métrica primária de regressão
de transcrição e CER (Character Error Rate) como métrica secundária —
especialmente adequada ao português por causa da rich morphology e de
erros de acentuação. Implementação via biblioteca `jiwer` com normalização
de texto explícita e documentada. O smoke test antigo é **preservado**
(sem alteração) como teste de integração de pipeline de sistema real.

**Alternativas:**
- Manter contagem de termos: rejeitado — insensível a regressão de qualidade.
- BLEU/ROUGE: rejeitado — métricas de geração, não de transcrição.
- Implementar WER manual: rejeitado — `jiwer` é padrão de mercado, testada.

**Consequências:** Nova dependência de dev (`jiwer`), leve e pura. Limiares
por categoria de cenário ficam no manifesto do corpus, não hard-coded.

**Reverter:** Remover `jiwer` do extra `[fidelity]` e excluir
`tests/fidelity/test_transcription_wer.py`.

---

## D-002 — Métrica de diarização: DER via pyannote.metrics (extra opcional)

**Data:** 2026-09-10 (UTC)

**Contexto:** O produto tem diarização implementada (`src/audio/diarize.py`
com diart/pyannote.audio), mas não há validação objetiva de qualidade em
áudio real. `pyannote.metrics` puxa árvore de dependências pesada
(torch/pyannote) que não deve entrar no job padrão de PR.

**Decisão:** Harness de DER com RTTM de referência sintético versionado no
corpus. Quando o extra `.[diarization-metrics]` estiver instalado, o DER é
computado com `pyannote.metrics.diarization.DiarizationErrorRate` (collar
0.0 e política de overlap documentada). Sem o extra, o teste valida o
harness (parse RTTM, mapeamento de labels, integração da métrica) e faz
skip explícito da computação DER real. O teste com diart/pyannote real é
marcado `requires_hf_token` e só roda com token + termos aceitos.

**Alternativas:**
- Implementar DER manual: rejeitado — fórmula de DER tem sutilezas
  (confusão de falantes, overlap) que `pyannote.metrics` já resolve.
- Exigir pyannote.metrics no job de PR: rejeitado — árvore pesada
  (torch) tornaria o pipeline de PR lento.

**Consequências:** DER em áudio pseudo-falado sintético valida contrato e
harness, **não** qualidade de embeddings em vozes humanas — declarado
explicitamente no teste e no README. Lacuna de corpus consentido humano
documentada.

**Reverter:** Remover extra `[diarization-metrics]` e o arquivo
`tests/fidelity/test_diarization_der.py`.

---

## D-003 — Fixtures 100% sintéticas, determinísticas por seed

**Data:** 2026-09-10 (UTC)

**Contexto:** A suíte precisa de corpus versionável sem voz pessoal,
reunião real ou material confidencial (regra de segurança do repositório).
Datasets públicos de fala (LibriSpeech, Common Voice) exigiriam download
grande e termos de licença específicos no runner.

**Decisão:** Todos os fixtures são gerados por código com seed explícita
(numpy `default_rng`). O gerador (`tests/fixtures/signal_generators.py`)
produz senoide, silêncio, ruído branco com RMS controlado, sinal
pseudo-fala (modulação AM/FM reproduzível sem chamada externa), mix de
pseudo-falantes com timeline conhecida, clipping, dropout e reamostragem.
Pequenos (≤ ~100 KB cada) e regeneráveis por `scripts/gen_fidelity_fixtures.py`.

**Alternativas:**
- Espeak-ng para pseudo-fala: rejeitado como dependência do corpus
  versionado (depende de binário do sistema e qualidade varia por versão) —
  mas é usado no teste de integração real existente, que permanece.
- Dataset público de fala: adiado por licença/tamanho; documentado como
  lacuna para WER representativo.

**Consequências:** WER medido sobre pseudo-fala sintética **não é
representativo** de WER em fala humana — documentado. A infraestrutura de
métrica fica pronta para receber corpus consentido.

**Reverter:** Remover `scripts/gen_fidelity_fixtures.py` e
`tests/fixtures/`.

---

## D-004 — Golden master guarda só medições estáveis; freeze exige flag

**Data:** 2026-09-10 (UTC)

**Contexto:** Golden master que inclui valores não determinísticos
(wall-clock, jitter absoluto) gera falsos positivos e "golden rotativo".
A referência audio-suite usa tolerâncias por métrica derivadas
empiricamente e regeneração exigindo label explícito.

**Decisão:** Golden guarda: hash SHA-256 da fixture, duração, contagem de
frames, RMS, pico espectral e tolerâncias por métrica. `python
scripts/fidelity_golden.py verify` compara; `python
scripts/fidelity_golden.py freeze --confirm-golden-regen` regenera — e
**falha** sem a flag. Nada de wall-clock/jitter no golden. Tolerâncias
derivadas de variância numérica de float, não de tempo.

**Alternativas:**
- Golden com hash de bytes exato: rejeitado — quebra em qualquer
  variação de libsndfile/numpy entre plataformas; medições físicas são
  mais estáveis que bytes crus.
- Snapshot de arquivo inteiro: rejeitado — difícil de revisar.

**Consequências:** Revisão de PR consegue ver diff de golden em YAML.
Atualização sem justificativa é detectável por convenção de commit
`golden-regen` (política no README).

**Reverter:** Remover `tests/golden/` e `scripts/fidelity_golden.py`.

---

## D-005 — Separação: job de PR offline x job real opt-in/noturno

**Data:** 2026-09-10 (UTC)

**Contexto:** Testes de hardware (PipeWire/WASAPI loopback), modelos STT e
diarização exigem recursos indisponíveis no runner hospedado do GitHub
(ubuntu-latest sem áudio, sem GPU, sem token HF no PR de fork).

**Decisão:** O job de PR (`ci.yml`) roda apenas: lint, suíte offline
(unit/fidelity/golden/contracts/fuzz limitado/performance smoke) — sem
hardware, sem token, sem download de modelo. Workflow separado
`audio-fidelity.yml` (workflow_dispatch + schedule noturno) roda os testes
marcados `real_audio`/`requires_pipewire`/`requires_hf_token`, com skip
explícito quando o recurso não existe — nunca sucesso simulado. Sem
runner self-hosted configurado, os jobs reais do workflow noturno executam
e reportam skips honestamente.

**Alternativas:**
- Rodar tudo no PR: rejeitado — pipeline lento e dependente de recursos
  inexistentes.
- Não versionar CI de teste real: rejeitado — perderia rastreabilidade.

**Consequências:** PR rápido (~minutos); cobertura real fica visível como
skip rastreável, não como falso verde.

**Reverter:** Remover workflow `audio-fidelity.yml` e o job `fidelity`
de `ci.yml`.

---

## D-006 — Tratamento da dependência opcional do pyannote (skip, não fail)

**Data:** 2026-09-10 (UTC)

**Contexto:** `pyannote.metrics` e `diart`/`pyannote.audio` são pesados
(torch) e o diart real exige token HF com termos aceitos previamente.

**Decisão:** Extra separado `[diarization-metrics]` (pyannote.metrics) para
o harness DER offline. Testes que dependem de extras fazem
`pytest.importorskip` com motivo preciso. O teste real de diarização é
marcado `requires_hf_token` e verifica `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN`
por referência de ambiente — o valor nunca é ecoado.

**Alternativas:**
- Instalar tudo em dev: rejeitado — pesado demais para o PR.
- Falhar quando ausente: rejeitado — tornaria CI vermelho sem causa real.

**Consequências:** Skips são explícitos e contáveis no relatório JSON.

**Reverter:** Remover extras e markers.

---

## D-007 — Testes de timing usam relógio monotônico injetado, não wall-clock absoluto

**Data:** 2026-09-10 (UTC)

**Contexto:** Testes de jitter/latência baseados em wall-clock absoluto em
runner compartilhado geram flakiness crônica.

**Decisão:** Testes de jitter p95 e budget de performance usam streams
sintéticos com relógio simulado determinístico (função de tempo injetável)
ou deadlines generosos rotulados `smoke budget`. O job noturno/self-hosted
pode configurar budgets p95 de produção via variáveis de ambiente
documentadas.

**Alternativas:**
- Wall-clock absoluto como gate rígido de PR: rejeitado — flaky.

**Consequências:** CI estável; medição real de produção fica no job
noturno configurável.

**Reverter:** Ajustar `tests/performance/test_capture_latency_budget.py`.
