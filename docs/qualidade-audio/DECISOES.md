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

---

## D-008 — Achado: WASAPI sem PyAudio não propaga erro de start() ao chamador

**Data:** 2026-09-10 (UTC)

**Contexto:** Durante os testes de conformance (CONF-03), observou-se que
``WasapiLoopbackCapture.start()`` em ambiente sem PyAudio instala a exceção
(ImportError) **dentro da thread interna** de captura: o chamador não
recebe erro explícito, ``is_running`` permanece True até ``stop()`` e a
fila permanece vazia — falha silenciosa.

**Decisão:** Documentar o comportamento como teste de registro
(``TestWasapiKnownLimitation``) e risco conhecido. **Não corrigir nesta
PR**: a correção exige propagação de erro assíncrona (callback ou evento)
e validação em Windows real, fora do escopo da suíte de testes e do
ambiente do agente (Linux, sem PyAudio/hardware).

**Alternativas:**
- Corrigir agora com try/except na thread + flag de erro: rejeitado —
  mudança de comportamento de produção sem como validar em Windows.
- Ignorar o achado: rejeitado — rastreabilidade exige registro.

**Consequências:** Risco baixo (PyAudio é dependência obrigatória no
fluxo Windows documentado); issue recomendada para PR dedicada.

**Reverter:** N/A (registro de comportamento, sem mudança de código).

---

## D-009 — Achado: fallback espectral degrada SNR de fala; budgets como tripwire

**Data:** 2026-09-10 (UTC)

**Contexto:** Medição de baseline local (scripts/measure_noise_baseline.py)
antes de fixar qualquer budget de SNR (regra do plano): o fallback espectral
do `RNNoiseFilter` (ativado quando pyrnnoise/rnnoise-wrapper não estão
instalados) **degrada** o SNR de fala+ruído @10 dB em ~7.3 dB e reduz o SNR
do sinal limpo a ~3.2 dB. O que funciona: gate de silêncio (saída ~0) e
atenuação de ruído puro (−4.8 dB). Causa provável: spectral subtraction sem
overlap-add, com compensação de janela agressiva.

**Decisão:** NÃO fingir qualidade: o teste RUIDO-01 mede e reporta o SNR
real e adota gates honestos por backend — RNNoise real deve melhorar ≥1 dB
(opt-in); fallback espectral é monitorado por tripwire de regressão
(degradação ≤ 12 dB, baseline medido 7.3). Registrar a limitação como
questão conhecida e recomendar RNNoise nativo em produção.

**Alternativas:**
- Assumir "filtro melhora SNR" como gate universal: rejeitado — falharia
  de imediato no fallback e esconderia o achado.
- Corrigir o fallback nesta PR: rejeitado — mudança de algoritmo de
  produção fora do escopo da suíte de testes.

**Consequências:** CI não fica vermelho por comportamento preexistente
documentado; regressões catastróficas do fallback são detectadas.

**Reverter:** Ajustar budgets em `scripts/gen_fidelity_fixtures.py` (seção
`budgets.noise`) e regenerar o manifesto.

---

## D-010 — CI de PR com dependências leves (`pip install -e . --no-deps`)

**Data:** 2026-09-10 (UTC)

**Contexto:** O job `fidelity` do CI de PR não precisa de torch,
transformers, customtkinter nem openai (a suíte offline não os importa),
mas precisa do pacote instalado para `import src.*`.

**Decisão:** Job instala manualmente as deps leves (numpy, scipy,
soundfile, PyYAML, jsonschema, jiwer, hypothesis, pytest, structlog,
python-dotenv) + `pip install -e . --no-deps`. O job `test` existente
(com `requirements.txt` completo) permanece inalterado.

**Alternativas:**
- `pip install -e ".[fidelity]"`: puxaria TODAS as deps de runtime
  (torch ~2 GB) — rejeitado por tempo de pipeline de PR.
- Extras auto-referentes (`dev>=0`): rejeitado — resolve pacote PyPI de
  mesmo nome (risco de supply chain).

**Consequências:** PR rápido (~1-2 min no job fidelity); risco baixo de
divergência de deps (documentado: src.* importa apenas deps leves nos
caminhos exercitados).

**Reverter:** Remover job `fidelity` do ci.yml.

---

## D-011 — Secret scanning direcionado com adjudicação explícita

**Data:** 2026-09-10 (UTC)

**Contexto:** Regra de segurança exige varredura de segredos nos arquivos
alterados antes de concluir. Padrões genéricos (hex 64+) geram falso
positivo nos SHA-256 de fixtures dos manifests.

**Decisão:** `scripts/secret_scan_changed_files.py` varre todos os
arquivos alterados vs main com padrões reais (GitHub PAT classic/fine,
gho_/ghr_, HF, OpenAI/Anthropic, AWS AKIA, blocos de private key,
bearer longo, atribuições .env). Falsos positivos conhecidos são
**adjudicados em código com justificativa** (sha256 de fixture nos dois
manifests), não ignorados informalmente. O scanner nunca imprime o
conteúdo suspeito — apenas arquivo+padrão.

**Alternativas:**
- gitleaks/trufflehog externos: adiado (requer instalação/CI dedicado);
  o scanner interno cobre o requisito desta PR.

**Consequências:** Varredura reproduzível localmente e no CI; resultado:
0 achados não adjudicados (ver RELATORIO-EXECUCAO.md §10).

**Reverter:** Remover o script.

---

## D-012 — Bloqueio: token sem `Contents:Write` impede push da branch/PR

**Data:** 2026-09-10 (UTC)

**Contexto:** O token GitHub fornecido para a missão (fine-grained PAT,
escopo `danzeroum/gravadorlegendas`) autentica corretamente (identidade
confirmada via API 200), porém concede **apenas leitura** de Contents
("code") — sem permissão de escrita. Evidências empíricas:

- `git push` → `403 Permission to danzeroum/gravadorlegendas.git denied`;
- `POST /repos/.../git/refs` (Git Data API) → `"Resource not accessible
  by personal access token"`;
- `git ls-remote` (leitura) → funciona;
- permissões do token: Read/Write em actions/issues/pull-requests/etc.,
  mas Contents apenas Read.

Sem `Contents:Write` não é possível: criar a branch remota, enviar os
commits ou, consequentemente, abrir a PR (que exige head existente).

**Decisão:** NÃO contornar o limite do token (ex.: escalar via
Actions/workflow para obter escrita seria burlar a fronteira de
permissão intencional — vedado pelas regras de segurança da missão).
Entrega da melhor implementação segura possível:

1. Branch completa e verificada localmente
   (`feat/audio-fidelity-test-suite`, 13 commits atômicos);
2. `git bundle` + série de patches para push imediato pelo mantenedor
   (um comando);
3. Descrição completa da PR pronta (`docs/qualidade-audio/PR-DESCRIPTION.md`);
4. Issue GitHub precisa documentando o bloqueio (issues:write concedido);
5. Documentação total do bloqueio (esta decisão, CHANGELOG,
   RELATORIO-EXECUCAO).

**Alternativas:**
- Escalar permissão via workflow_dispatch + GITHUB_TOKEN com
  contents:write: rejeitado — contorno de fronteira de segurança.
- Push para fork: inviável — PAT single-repo não cobre novos repositórios.
- Declarar a PR como feita: rejeitado — sucesso simulado é vedado.

**Consequências:** A PR fica pronta para abertura em um passo manual
(push + `gh pr create --fill` ou colar a descrição). Todo o resto da
definição de pronto foi cumprido.

**Reverter:** N/A (registro de bloqueio).

---

## D-013 — Bloqueio: PAT sem permissão `Workflows` rejeita push que versiona CI

**Data:** 2026-09-10 (UTC)

**Contexto:** Após o desbloqueio de D-012 (token reemitido com
`Contents: Read and write`), o `git push` autenticou com sucesso e
alcançou o GitHub, mas foi rejeitado com mensagem completa e inequívoca:

    ! [remote rejected] feat/audio-fidelity-test-suite -> feat/audio-fidelity-test-suite
    (refusing to allow a Personal Access Token to create or update workflow
    `.github/workflows/audio-fidelity.yml` without `workflow` scope)

A entrega versiona arquivos em `.github/workflows/` (job `fidelity` em
`ci.yml` e workflow noturno `audio-fidelity.yml` — requisitos CI-01..03),
e o GitHub exige a permissão **Workflows** (leitura e escrita) para
pushes que criam/alteram esses arquivos: proteção legítima contra
escalonamento de privilégio via execução de workflow.

**Decisão:** Mesmo princípio de D-012 — diagnóstico preciso e NENHUM
contorno. Descartados por evidência: bug de variável de ambiente perdida
(token exportado e consumido no mesmo comando; o push autenticou e
alcançou o servidor); 403 de Contents (resolvido pelo reemitimento).
Ação requerida do mantenedor: reemitir o PAT acrescentando
**Workflows → Read and write** (demais permissões inalteradas).
Registrado também na issue #4 (comentário interino com a mensagem
completa). O tempo de espera foi convertido em hardening pré-push
(D-014/D-015): a branch chega ao remoto já CI-ready.

**Alternativas:**
- Push parcial sem os commits de workflow: inviável — exigiria rewrite
  de histórico (vedado) e amputaria o CI da entrega (CI-01..03).
- Criar refs/commits via Git Data API: rejeitado — a mesma proteção se
  aplica ao conteúdo; além de caminho não padrão de força.
- Fork: inviável — PAT single-repo, fora do escopo da missão.

**Consequências:** Push/PR aguardam ação do mantenedor; tudo o mais
permanece pronto e verificado. Resolução será registrada em adendo datado
do RELATORIO-EXECUCAO.md quando ocorrer.

**Reverter:** N/A (registro de bloqueio).

---

## D-014 — Coleção graciosa da suíte de fidelidade sem deps opcionais

**Data:** 2026-09-10 (UTC)

**Contexto:** O job `test` do CI instala apenas `requirements.txt`
(numpy/PyYAML chegam transitivamente via transformers; scipy, soundfile,
hypothesis, jiwer e jsonschema NÃO). Os módulos das suítes novas importam
essas deps no nível de módulo (hypothesis em fuzz/WER; soundfile em
integridade sinal e via `scripts.fidelity_golden` no golden) ou em
runtime via import lazy (scipy em `sg.resample` usado por MET-03;
jsonschema no validador usado pelos contratos). Evidência red→green em
ambiente simulado do job `test` (venv sem as deps opcionais):

- **Antes:** 4 erros de coleta (`hypothesis`×2, `soundfile`×2) + 3
  falhas de runtime em MET-03 (`scipy` lazy em `resample_poly`); 98
  testes coletados que falhariam parcialmente em runtime.
- **Depois:** 0 erros; as 4 suítes fora da coleção com nota explícita no
  header do pytest; árvore completa com 245 coletados e apenas os 9
  erros UI preexistentes (fora de escopo; ausentes no runner real, que
  instala requirements.txt completo).

**Decisão:** Guarda central no conftest raiz: quando qualquer dep
opcional estiver ausente, os diretórios fidelity/golden/contracts/
performance saem da coleção via `collect_ignore_glob`, com nota no
cabeçalho (`pytest_report_header`) apontando o dono real desses testes
(job `fidelity` do CI; local: `pip install -e .[fidelity]`). Import de
`yaml` no conftest raiz tornado lazy. Suíte completa revalidada com deps
presentes: guarda inerte (197/2/1 idêntico ao documentado; regressão de
áudio 108/1 idêntica à baseline; flake8 0 violações).

**Alternativas:**
- `importorskip` por módulo: rejeitado — espalhado e inconsistente entre
  4 diretórios e ~15 módulos.
- Adicionar as deps ao requirements.txt: rejeitado — pesaria a instalação
  mínima do produto (regra: produto inalterado).
- Deixar como estava e aceitar CI vermelho no job `test`: rejeitado —
  falso sinal de regressão onde há apenas ausência de deps opcionais.

**Consequências:** Job `test` permanece dono da suíte do produto; job
`fidelity` é o dono único e completo das suítes de fidelidade. DER real
com pyannote.metrics permanece no workflow noturno, por design das fases
7/9 (no job `fidelity` do PR os testes DER saem da coleção — skip
rastreável, nunca falha mascarada).

**Reverter:** Remover o bloco `_FIDELITY_*` do `tests/conftest.py`.
