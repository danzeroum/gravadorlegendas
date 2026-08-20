# Status de Validação — gravadorlegendas Fedora Multiplatform

**Data de geração:** 2026-08-20
**Branch:** `feat/linux-fedora-support`
**Commit HEAD:** (a ser preenchido no empacotamento)
**Status global:** ⚠️ **PENDENTE DE VALIDAÇÃO REAL EM FEDORA DESKTOP**

---

## Resumo objetivo

A implementação está **completa em código** e **validada por testes unitários,
lint e inspeção estática**, mas **NÃO foi validada em Fedora desktop real**
com PipeWire ativo, microfone físico e modelo STT local baixado.

**Os testes E2E obrigatórios (E2E-01 até E2E-10) NÃO foram executados em
ambiente real.** Portanto, **NÃO se pode declarar "Fedora funcionalmente
validado"** conforme exigido pela regra de aprovação.

Este ZIP **NÃO** leva o sufixo `-verified` no nome.

---

## Ambiente de validação utilizado

### Ambiente A — contêiner headless (atual)

| Item | Valor |
|------|-------|
| OS | Linux (Alibaba Cloud Linux, kernel 5.10) |
| Distribuição | NÃO é Fedora — contêiner genérico |
| Python | 3.12.13 |
| `XDG_SESSION_TYPE` | não definido (headless) |
| `DISPLAY` | não definido |
| `WAYLAND_DISPLAY` | não definido |
| PipeWire | não instalado |
| `pactl` | não disponível |
| `pw-record` | não disponível |
| Tesseract | 5.x em `/usr/bin/tesseract` (sem langpack português) |
| Modelo Whisper | não baixado |
| Microfone | nenhum |
| GPU | nenhuma |

**Comandos de coleta de ambiente (não executados por falta de Fedora real):**

```bash
cat /etc/fedora-release           # N/A — não é Fedora
uname -a                          # Linux ... x86_64 GNU/Linux
python3 --version                 # Python 3.12.13
pw-cli info 0                     # N/A — pw-cli não instalado
systemctl --user status pipewire  # N/A
pactl info                        # N/A
pactl list short sources          # N/A
pactl list short sinks            # N/A
echo "$XDG_SESSION_TYPE"          # (vazio)
```

### Ambiente B — Fedora desktop real (pendente)

**Não disponível nesta execução.** Para validar, é necessário provisionar:

- VM ou máquina física com Fedora Workstation 40+ ou Fedora KDE
- PipeWire ativo por padrão
- `pipewire-pulseaudio`, `pipewire-utils` instalados
- Tesseract + `tesseract-langpack-por` + `tesseract-langpack-eng`
- Microfone físico ou fonte virtual (`pactl load-module module-null-sink`)
- Saída de áudio funcional (alto-falante ou fone)
- Navegador ou player para reproduzir áudio de teste
- Modelo Whisper `base` baixado em `~/.cache/gravador/audio/whisper/base/`

---

## Matriz de testes — status por cenário

### Testes unitários (CI headless — Ambiente A)

| Comando | Resultado | Duração |
|---------|-----------|---------|
| `pytest -q -m "not integration"` | ✅ 152 passed, 22 deselected | 11.17s |
| `pytest -q` (sem filtro) | ✅ 152 passed, 22 skipped | 10.28s |
| `python3 -m flake8 src/ --max-line-length=100 --extend-ignore=E501,W503,E203` | ✅ limpo (0 avisos) | <1s |
| `pytest -q -m "integration and requires_pipewire"` | ⏸️ 11 skipped (sem PipeWire) | 0.11s |
| `pytest -q -m "integration and requires_stt_model"` | ⏸️ 3 skipped (sem modelo) | 0.07s |
| `pytest -q -m "integration and requires_x11"` | ⏸️ 4 skipped (sem X11) | 0.08s |
| `pytest -q -m "integration and requires_display"` | ⏸️ 4 skipped (sem display) | 0.08s |

### Testes E2E obrigatórios (Ambiente B — Fedora desktop real)

| ID | Cenário | Status | Evidência |
|----|---------|--------|-----------|
| E2E-01 | Instalação limpa Fedora | ⏳ PENDENTE | Requer Fedora real |
| E2E-02 | Inicialização da aplicação | ⏳ PENDENTE | Requer Fedora desktop |
| E2E-03 | Detecção PipeWire | ⏳ PENDENTE | Requer PipeWire ativo |
| E2E-04 | Detecção de microfone | ⏳ PENDENTE | Requer microfone |
| E2E-05 | Detecção de áudio do sistema | ⏳ PENDENTE | Requer sink ativo |
| E2E-06 | Captura de microfone | ⏳ PENDENTE | Requer microfone + PipeWire |
| E2E-07 | Captura do sistema | ⏳ PENDENTE | Requer player + monitor |
| E2E-08 | Start/stop repetido | ⏳ PENDENTE | Requer PipeWire |
| E2E-09 | Transcrição local | ⏳ PENDENTE | Requer modelo Whisper |
| E2E-10 | Pipeline completo | ⏳ PENDENTE | Requer tudo acima |
| E2E-11 | OCR em X11 | ⏳ PENDENTE | Requer X11 + Tesseract PT |
| E2E-12 | Wayland | ⏳ PENDENTE | Requer Wayland |
| E2E-13 | Seleção de dispositivo | ⏳ PENDENTE | Requer 2+ dispositivos |
| E2E-14 | Ausência de PipeWire | ✅ Validado por teste unitário | `test_e2e_14_no_pipewire_graceful_failure` (pula em ambiente real, mas valida o caminho feliz em testes unitários) |
| E2E-15 | Regressão Windows isolada | ✅ Validado por teste unitário | `test_e2e_15_wasapi_never_on_linux` e `test_platform_selector.py::test_wasapi_on_linux_raises` |

### Detalhamento do que foi validado vs. pendente

#### ✅ Validado por teste unitário (com mocks)

- Detecção de OS/sessão/capacidades em Windows, Linux, Wayland, X11, headless.
- Seleção automática de backend com fallback gracioso.
- Backend WASAPI jamais selecionado em Linux.
- Backend PipeWire não selecionado em Windows.
- Legendas ao Vivo do Windows não chamadas em Linux (`WindowsLiveCaptionsSource` levanta `CaptionSourceError` na construção).
- Validação de configurações inválidas (`audio_backend=wasapi` em Linux, etc.).
- Fallback `auto` → `local_stt` em Linux.
- Formato de chunks PCM s16le 16kHz mono compatível com pipeline.
- Parser de `pactl list sources` (com fixture sintética).
- Lifecycle de `PipewireCapture` (start/stop idempotente, build_cmd correto).
- Detecção de Wayland e `ScreenCaptureError` clara.
- `os.startfile` substituído por `_open_folder_crossplatform`.

#### ⏳ Pendente de validação real em Fedora desktop

- **E2E-01 a E2E-10**: fluxo completo de áudio com PipeWire real.
- **E2E-11**: OCR em X11 com Tesseract + langpack português real.
- **E2E-12**: comportamento em Wayland (validar que o app não crashe, exibe banner correto, etc.).
- **E2E-13**: seleção manual entre microfone e monitor reais.
- Ausência de processos `pw-record` órfãos após 5 ciclos.
- Transcrição de fala real em português com texto não vazio.

---

## Limitações explícitas remanescentes

### 1. Captura de tela em Wayland via portal (NÃO implementada)

- **Status**: Não implementado.
- **Comportamento**: Em Wayland sem `xdg-desktop-portal`, `ScreenCapture.capture()` lança `ScreenCaptureError` com mensagem orientando fallback para X11.
- **Plano**: Ver seção 8.1 do `RELATORIO_MIGRACAO_FEDORA.md`.

### 2. `audio_source=both` (NÃO implementado)

- **Status**: A opção é validada em `validate_settings()` mas o `AudioManager` não implementa mixagem microfone+sistema.
- **Comportamento**: Apenas `device_index` único é suportado por vez.
- **Plano**: Implementar mixagem downmix em `AudioManager` em versão futura.

### 3. Diarização não testada em Linux

- **Status**: Código preservado intacto, mas sem validação.
- **Comportamento**: Teoricamente multiplataforma (`diart` é puro Python + PyTorch).
- **Plano**: Teste manual em Fedora com token HF configurado.

### 4. PipeWire via `pw-record` (sem teste de captura real)

- **Status**: Lógica de subprocess validada por teste unitário com mocks, mas sem captura de áudio real.
- **Comportamento**: Em Fedora real com PipeWire ativo, o `pw-record` deve funcionar — mas isso não foi confirmado.
- **Plano**: Rodar `pytest -q -m "integration and requires_pipewire"` em Fedora desktop.

### 5. Transcrição local (sem teste com fala real)

- **Status**: Pipeline faster-whisper integrado, mas sem validar transcrição de fala humana real.
- **Comportamento**: `test_e2e_09_transcription_produces_text` valida que o pipeline não quebra com áudio sintético, mas onda senoidal 440Hz não produz texto reconhecível.
- **Plano**: Fornecer fixture WAV com frase conhecida (ex: "Olá, este é um teste") e validar texto não vazio.

---

## Roteiro para validação real em Fedora desktop

### Pré-requisitos

```bash
# Fedora Workstation 40+ ou Fedora KDE
sudo dnf install -y \
  python3 python3-pip python3-tkinter \
  tesseract tesseract-langpack-por tesseract-langpack-eng \
  pipewire pipewire-utils pipewire-pulseaudio \
  pulseaudio-libs-utils \
  gcc gcc-c++ make

# Verificar
cat /etc/fedora-release
pw-cli info 0
systemctl --user status pipewire pipewire-pulse --no-pager
pactl info
pactl list short sources
pactl list short sinks
echo "$XDG_SESSION_TYPE"
```

### Passo 1: instalação

```bash
git clone -b feat/linux-fedora-support <repo>
cd gravadorlegendas
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[linux,audio,dev]"
```

### Passo 2: rodar testes unitários (sanidade)

```bash
pytest -q -m "not integration"    # deve passar 152
python3 -m flake8 src/            # deve estar limpo
```

### Passo 3: rodar testes de integração PipeWire

```bash
pytest -q -m "integration and requires_pipewire" -v
```

Cenários cobertos: E2E-03, E2E-04, E2E-05, E2E-06, E2E-07, E2E-08, E2E-13, E2E-14, E2E-15.

### Passo 4: baixar modelo Whisper e rodar teste STT

```bash
python3 scripts/setup_audio_models.py   # baixa modelo base
pytest -q -m "integration and requires_stt_model" -v
```

Cenários cobertos: E2E-09 (parcial — áudio sintético não é fala).

### Passo 5: rodar teste OCR em X11

```bash
# Faça logout e entre em sessão Xorg se estiver em Wayland
pytest -q -m "integration and requires_x11" -v
```

Cenários cobertos: E2E-11.

### Passo 6: validar Wayland

```bash
# Faça logout e entre em sessão Wayland
pytest -q -m "integration and requires_display" -k wayland -v
```

Cenários cobertos: E2E-12.

### Passo 7: coletar evidências

Após rodar todos os testes, gerar relatório em `artifacts/validation/`:

```bash
pytest -q -m "integration" -v --json-report --json-report-file=artifacts/validation/e2e_results.json
```

---

## Regra de aprovação — verificação

| # | Regra | Status |
|---|-------|--------|
| 1 | Testes unitários e lint passam | ✅ Sim |
| 2 | E2E-01 até E2E-10 passam em Fedora desktop | ❌ Não executados |
| 3 | E2E-12 (Wayland) documentado e seguro | ⚠️ Teste existe mas não rodou |
| 4 | Sem processos `pw-record` órfãos | ❌ Não validado (sem PipeWire) |
| 5 | Transcrição local validada com áudio real | ❌ Não validado |
| 6 | Limitações explícitas no README e relatório | ✅ Sim |

**Conclusão**: 3 de 6 regras atendidas. **A implementação NÃO pode ser marcada como "Fedora funcionalmente validado".**

---

## Próximos passos obrigatórios antes de declarar "verified"

1. Provisionar VM Fedora Workstation 40+ com PipeWire ativo.
2. Instalar dependências conforme README.
3. Baixar modelo Whisper `base`.
4. Conectar microfone físico ou criar fonte virtual.
5. Reproduzir áudio de teste (navegador/player).
6. Rodar todos os testes de integração e coletar evidências.
7. Validar ausência de `pw-record` órfãos: `pgrep -c pw-record` deve retornar 0 após todos os testes.
8. Validar transcrição de fala real: fornecer WAV com frase conhecida e confirmar texto não vazio.
9. Validar OCR em X11 com texto PT conhecido na tela.
10. Validar Wayland: app inicia, banner vermelho aparece, captura falha com mensagem clara.
11. Após tudo passar, renomear o ZIP para `gravadorlegendas-fedora-multiplatform-<YYYYMMDD>-verified.zip`.

---

## Conclusão

A implementação está **arquiteturalmente completa e testada unitariamente**,
mas **a validação funcional real em Fedora desktop é uma pendência
que exige ambiente que não está disponível nesta execução**.

Nenhum commit foi feito direto na `main`. Todos os commits estão na branch
`feat/linux-fedora-support`. O ZIP entregue contém o código completo,
os testes de integração prontos para rodar (com skip gracioso quando os
pré-requisitos não estão disponíveis), e este arquivo `VALIDATION_STATUS.md`
documentando objetivamente o que foi e o que não foi validado.
