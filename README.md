# Gravador de Legendas

Captura, transcreve, traduz e processa legendas em tempo real com OCR,
captura de áudio, diarização de falantes e LLM local — **multiplataforma**
(Windows + Fedora Linux, com suporte parcial a Wayland).

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platforms: Windows + Linux](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20Fedora-green.svg)](#instalação)
[![tests](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml/badge.svg)](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml)

---

## Funcionalidades

- **Captura de tela** — região configurável, OCR com suporte a múltiplos idiomas (inglês, português, espanhol). Funciona em X11 e Windows; Wayland requer `xdg-desktop-portal`.
- **Tradução local** — MarianMT (`opus-mt-tc-big-en-pt`) com fallback para API (OpenAI / DeepSeek).
- **Áudio ao vivo** — captura multiplataforma:
  - **Windows**: WASAPI loopback (PyAudio).
  - **Linux (Fedora)**: PipeWire via `pw-record` (microfone e áudio do sistema).
- **Transcrição local** — `faster-whisper` (CPU ou CUDA).
- **VAD** — `silero-vad` para detecção de fala.
- **Diarização** — identificação de falantes em tempo real ou offline (diart + pyannote.audio).
- **Exportação** — transcrição com rótulos de falante em Markdown.
- **LLM pluggável** — Ollama (Basic Auth + NDJSON), OpenAI, DeepSeek, LocalGGUF.
- **Resumo automático** da reunião via LLM, incluindo contexto de áudio + OCR.
- **Detecção de perguntas** e sugestão de respostas em Globish.
- **Filtro de ruído** do OCR com wordlist e heurísticas.
- **Interface gráfica** CustomTkinter com 7 abas, adaptando-se por capacidade (não por SO).
- **Servidor HTTP** (FastAPI) para implantação em Docker/VPS.

---

## Pré-requisitos

### Comuns a todas as plataformas

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) instalado no sistema
  - Pacotes de idioma: português (`por`) e inglês (`eng`)
- (Opcional) GPU NVIDIA com CUDA para acelerar `faster-whisper`
- (Opcional) Conta [Hugging Face](https://huggingface.co) com token aceito para `pyannote/speaker-diarization-3.1`

### Fedora Linux — pacotes de sistema

```bash
sudo dnf install -y \
  python3 python3-pip python3-tkinter \
  tesseract tesseract-langpack-por tesseract-langpack-eng \
  pipewire pipewire-utils pipewire-pulseaudio \
  pulseaudio-libs-utils \
  gcc gcc-c++ make
```

> **Por que esses pacotes?**
>
> - `python3-tkinter` — CustomTkinter depende do Tk.
> - `tesseract-langpack-*` — OCR em português e inglês.
> - `pipewire` + `pipewire-utils` — servidor de áudio + `pw-record`/`pw-cli` para captura.
> - `pipewire-pulseaudio` — camada de compatibilidade PulseAudio (necessária para `pactl`, usado na descoberta de dispositivos).
> - `pulseaudio-libs-utils` — fornece `pactl` como fallback caso PipeWire-Pulse não esteja configurado.
> - `gcc`/`gcc-c++`/`make` — apenas se for compilar extensões nativas (geralmente não é necessário com wheels pré-compiladas).

### Windows

- Tesseract OCR: `choco install tesseract` ou [site oficial](https://github.com/UB-Mannheim/tesseract/wiki)
- PyAudio: geralmente pré-compilado via pip (`pip install PyAudio`)

---

## Instalação

### Fedora Linux

```bash
git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[linux,audio]"

# Copiar configuração de exemplo
cp .env.example .env
# Edite .env conforme necessário (provedores LLM, idioma OCR, etc.)
```

### Windows (PowerShell)

```powershell
git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[windows,audio]"

copy .env.example .env
```

### Diarização (opcional, em qualquer plataforma)

```bash
pip install -e ".[diarization]"
huggingface-cli login  # aceite os termos em pyannote/speaker-diarization-3.1
```

---

## Uso

### Interface Gráfica (Desktop)

```bash
python -m src.main
```

A nova tela principal prioriza o fluxo **captura de áudio → transcrição ao vivo → ações sobre o texto**:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Gravador de Legendas                  ● Pronto   [☀️ Claro] [⚙ Config]  │
├──────────────────────────────────────────────────────────────────────┤
│ Origem: [🔊 Áudio do sistema ▾]  [🔄]  [▶ Iniciar transcrição]  00:00:00 │
│                                                                      │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ Transcrição ao vivo                                    [Copiar][Salvar .txt][Exportar .md][Limpar] │
│ │ ┌──────────────────────────────────────────────────────────────┐ │ │
│ │ │ A fala transcrita aparece aqui, em fonte confortável, com     │ │ │
│ │ │ timestamps opcionais e rolagem automática controlável.        │ │ │
│ │ └──────────────────────────────────────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ [Traduzir] [Gerar resumo] [Responder]                              [◧ Painel]  │
├──────────────────────────────────────────────────────────────────────┤
│ Origem: 🔊 Monitor PipeWire • Modelo: base • Backend: PipeWire     │
└──────────────────────────────────────────────────────────────────────┘
```

- **Painel lateral recolhível** (▸ Painel): Tradução, Resumo, Resposta, Falantes — abre sob demanda.
- **Configurações** (`⚙`): modal com Aparência (tema, escala DPI, prefixo), IA, Captura OCR, Sistema.
- A captura OCR (tela) permanece disponível no modal Config → "Captura de tela", mas **não funciona em Wayland** sem portal.

#### Atalhos de teclado

| Atalho | Ação |
|--------|------|
| `Ctrl+R` | Iniciar/parar gravação (toggle) |
| `Ctrl+S` | Salvar transcrição como .txt |
| `Ctrl+L` | Limpar transcrição (com confirmação) |
| `Ctrl+,` | Abrir configurações |
| `Esc` | Fechar painel lateral ou diálogo modal |

#### Escala DPI (alta densidade / Fedora)

A interface respeita `APP_WIDGET_SCALING` (env) ou a preferência persistida em Configurações → Aparência → Escala da interface (90% / 100% / 110% / 125% / 140%).

- A escala aplica-se **apenas aos widgets** (`ctk.set_widget_scaling`); a janela permanece em 1.0 para evitar escala dupla.
- Mudanças de escala exigem **reinício da aplicação** (aviso exibido no diálogo).

### Modos de captura

#### Microfone (Linux)

1. Aba Áudio → clique em "🔄 Atualizar Dispositivos".
2. Selecione a fonte com prefixo `🎤` (input).
3. Clique em "🎤 Iniciar Captura".

#### Áudio do sistema (Linux)

1. **Pré-requisito**: precisa haver um sink de saída ativo (tocando som).
2. Aba Áudio → clique em "🔄 Atualizar Dispositivos".
3. Selecione a fonte com prefixo `🔊` (monitor).
4. Clique em "🎤 Iniciar Captura".
5. Se nenhuma fonte monitor aparecer, rode `python3 scripts/diagnose_linux_audio.py`.

#### Transcrição local (Linux e Windows)

- É o **modo padrão em Linux** (`caption_source=auto` resolve para `local_stt`).
- Requer `pip install -e ".[audio]"` (faster-whisper).
- O modelo Whisper é baixado automaticamente no primeiro uso para `~/.cache/gravador/audio/whisper/`.
- Para forçar modo STT local em Windows, defina `CAPTION_SOURCE=local_stt` no `.env`.

#### OCR de tela (opcional)

- Funciona em X11 e Windows via `mss`.
- Em Wayland sem `xdg-desktop-portal`, a captura falha com mensagem clara.
- **Workaround em Wayland**: faça logout e entre em sessão "Xorg" no gerenciador de login (GDM/SDDM/LightDM).

#### Wayland

- A aplicação **inicia** em Wayland sem crash.
- A aba Captura mostra banner vermelho avisando da limitação.
- A aba Áudio funciona normalmente (PipeWire é independente da sessão gráfica).
- Para OCR de tela, use sessão X11.

### Diagnóstico de áudio (Linux)

```bash
python3 scripts/diagnose_linux_audio.py
```

Mostra sistema operacional, sessão, status do PipeWire, fontes disponíveis
(microfones + monitores), sinks, permissões e orientações.

### Servidor HTTP (Docker)

```bash
docker-compose -f docker/docker-compose.yml up api
```

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check |
| POST | `/translate` | Tradução de texto |
| POST | `/summarize` | Resumo via LLM |
| POST | `/generate` | Geração de resposta Globish |
| GET | `/v1/llm/providers` | Listar providers disponíveis |
| GET | `/v1/llm/config` | Obter config ativa |
| POST | `/v1/llm/config` | Atualizar config LLM |
| POST | `/v1/llm/test` | Testar conexão com provider |

---

## Providers de LLM

| Provider | Autenticação | Streaming | Uso |
|----------|-------------|-----------|-----|
| **Ollama** | Basic Auth (user/pass) | NDJSON (`Accept: application/x-ndjson`) | Padrão — servidor remoto |
| **OpenAI** | API Key | SSE | Fallback de tradução |
| **DeepSeek** | API Key | SSE | Tradutor alternativo |
| **LocalGGUF** | Nenhuma | Nenhum | Modelo GGUF local (cpu) |

A configuração ativa é definida na aba **IA** da interface ou via API. O provider padrão é `ollama` apontando para `https://api.buildtovalue.cloud` com modelo `mistral:latest`.

---

## Estrutura do Projeto

```
src/
├── platform/                # NOVO — camada de abstração multiplataforma
│   ├── detection.py         #   detecta OS, sessão, capacidades
│   ├── types.py             #   AudioDevice, AudioCaptureBackend Protocol, etc.
│   └── selector.py          #   seleção automática de backends
├── audio/
│   ├── backends/            # NOVO — backends concretos
│   │   ├── wasapi/          #   Windows (PyAudio + WASAPI loopback)
│   │   ├── pipewire/        #   Linux (pw-record subprocess + pactl discovery)
│   │   └── factory.py       #   construção com seleção automática
│   ├── capture.py           #   Fachada retrocompatível (delegação)
│   ├── vad.py               #   Voice Activity Detection (silero-vad)
│   ├── buffer.py            #   Buffer circular thread-safe
│   ├── transcribe.py        #   Transcrição (faster-whisper em Process)
│   ├── diarize.py           #   Diarização de falantes (diart)
│   ├── manager.py           #   Orquestração com 2 filas + merge
│   ├── metrics.py           #   Latência e sobreposição
│   └── models.py            #   Download/cache de modelos
├── caption/                 # NOVO — fontes de legenda abstraídas
│   ├── base.py              #   CaptionSourceBase
│   ├── windows_live.py      #   Win+Ctrl+L (apenas Windows)
│   ├── local_stt.py         #   Transcrição local (Win + Linux)
│   ├── screen_ocr.py        #   OCR de tela (X11 + Windows)
│   └── factory.py           #   build_caption_source()
├── capture/                 # Captura de tela (mss) + ativação de legendas Windows
│   ├── screen_capture.py    #   agora detecta Wayland e dá erro claro
│   └── activate_windows_captions.py  # no-op defensivo em Linux
├── ocr/                     # OCR (pytesseract)
├── translation/             # Tradução (Strategy Pattern)
├── nlp/                     # Processamento de linguagem
├── filter/                  # Filtro de ruído do OCR
├── llm/                     # Sistema de LLM pluggável
├── storage/                 # Persistência em arquivo
├── ui/                      # Interface CustomTkinter (adaptativa por capacidade)
├── api/                     # Servidor HTTP (FastAPI)
├── config.py                # Configuração (.env) + validação multiplataforma
├── config_store.py          # Config JSON (LLM, speaker_map)
└── main.py                  # Orquestração (SessionManager)

scripts/
├── diagnose_audio_device.py    # Diagnóstico WASAPI (Windows)
├── diagnose_linux_audio.py     # NOVO — Diagnóstico PipeWire (Linux)
└── setup_audio_models.py       # Download de modelos Whisper/Silero

tests/                       # 152 testes — pytest
├── test_platform_detection.py  # NOVO
├── test_platform_selector.py   # NOVO
├── test_audio_backends.py      # NOVO
├── test_caption_sources.py     # NOVO
├── test_config_validation.py   # NOVO
└── ... (testes originais preservados)
```

---

## Configuração

Variáveis de ambiente (`.env`) — veja `.env.example` para o template completo.

### Multiplataforma (novo)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PLATFORM_BACKEND` | `auto` | `auto` \| `windows` \| `linux` |
| `AUDIO_BACKEND` | `auto` | `auto` \| `wasapi` \| `pipewire` |
| `AUDIO_SOURCE` | `system` | `microphone` \| `system` \| `both` \| `device` |
| `AUDIO_DEVICE_ID` | (vazio) | ID do dispositivo (vazio = padrão) |
| `CAPTION_SOURCE` | `auto` | `auto` \| `windows_live_captions` \| `local_stt` \| `screen_ocr` |
| `SCREEN_CAPTURE_BACKEND` | `auto` | `auto` \| `mss` \| `portal` |
| `STT_MODEL` | `base` | Tamanho do modelo Whisper |
| `STT_DEVICE` | `auto` | `auto` \| `cpu` \| `cuda` |
| `SAMPLE_RATE` | `16000` | Taxa de amostragem (Hz) |
| `CHANNELS` | `1` | Número de canais (1=mono) |

### Curto prazo (gravação dual-track, RNNoise, export SRT/VTT)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `RECORD_RAW_AUDIO` | `false` | Se `true`, ativa gravação dual-track (mic+sistema em WAVs separados). Os arquivos são salvos em `RECORDING_DIR` com sufixos `_mic.wav` e `_sistema.wav`. |
| `RECORDING_DIR` | `data/recordings` | Diretório onde transcrições `.txt` (e agora `.srt`/`.vtt`/`.wav`) são salvos. |
| `NOISE_SUPPRESSION` | `false` | Se `true`, ativa filtro de ruído RNNoise no pipeline de áudio (entre captura e Whisper). Reduz ruído de fundo em tempo real, mas adiciona latência — validar com `T5.2` antes de habilitar em produção. |
| `EXPORT_SRT` | `true` | Se `true`, gera arquivo `.srt` ao lado do `.txt` ao final da sessão. |
| `EXPORT_VTT` | `true` | Se `true`, gera arquivo `.vtt` ao lado do `.txt` ao final da sessão. |

### Tradicionais (preservadas)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `TESSERACT_PATH` | (auto) | Vazio = usar do PATH; Windows default: `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| `OCR_LANGUAGE` | `eng` | Idioma do OCR |
| `TRANSLATION_MODEL` | `Helsinki-NLP/opus-mt-tc-big-en-pt` | Modelo MarianMT |
| `OPENAI_API_KEY` | — | Chave da API OpenAI |
| `DEEPSEEK_API_KEY` | — | Chave da API DeepSeek |
| `OLLAMA_BASE_URL` | `https://api.buildtovalue.cloud` | URL do servidor Ollama |
| `OLLAMA_USERNAME` | — | Usuário Basic Auth |
| `OLLAMA_PASSWORD` | — | Senha Basic Auth |
| `OLLAMA_MODEL` | `mistral:latest` | Modelo Ollama |
| `REGION_TOP/LEFT/WIDTH/HEIGHT` | `0,50,1820,80` | Região de captura |

---

## Testes

```bash
# Todos os testes unitários (sem hardware, sem rede, sem GPU)
pytest -q

# Excluir testes de integração (default: nenhum marcado integration)
pytest -m "not integration"

# Com cobertura
pytest tests/ --cov=src

# Apenas testes da nova camada de plataforma
pytest tests/test_platform_detection.py tests/test_platform_selector.py -v
```

### Marcadores de teste

| Marcador | Significado |
|----------|-------------|
| `@pytest.mark.integration` | Exige hardware real ou rede |
| `@pytest.mark.requires_pipewire` | Exige PipeWire rodando |
| `@pytest.mark.requires_wasapi` | Exige Windows + WASAPI |
| `@pytest.mark.requires_display` | Exige sessão gráfica ativa |

Atualmente **nenhum teste** exige esses marcadores — todos rodam em CI headless.

---

## Troubleshooting

### PipeWire não está rodando

```bash
systemctl --user status pipewire pipewire-pulse
# Se não estiver ativo:
systemctl --user start pipewire pipewire-pulse
systemctl --user enable pipewire pipewire-pulse
```

Se o problema persistir após logout/login:

```bash
sudo dnf reinstall pipewire pipewire-pulseaudio
```

### Dispositivo de monitor não aparece na lista

1. Verifique se há um sink ativo: `pactl list sinks | grep -i state`
2. Toque qualquer som (música, vídeo) — o monitor é criado automaticamente quando há saída.
3. Rode o diagnóstico: `python3 scripts/diagnose_linux_audio.py`
4. Reinicie o PipeWire: `systemctl --user restart pipewire`

### Falta de permissões de áudio

- **Flatpak**: o aplicativo precisa da permissão `org.freedesktop.portal.Flatpak.app.*` (não aplicável aqui — não usamos Flatpak).
- **SELinux**: em raras configurações restritivas, o `pw-record` pode ser bloqueado. Verifique com `sudo ausearch -m AVC -ts recent | grep pw-record`.
- **Root**: **não rode como root** — PipeWire roda no espaço do usuário. Use usuário comum logado na sessão gráfica.

### Captura de tela bloqueada no Wayland

Sintomas: frame preto, erro "Captura de tela não suportada em Wayland via mss".

Soluções:

1. **Fazer logout e entrar em sessão Xorg** (recomendado):
   - GDM: na tela de login, clique na engrenagem e selecione "GNOME on Xorg".
   - SDDM (KDE): selecione "Plasma (X11)".
2. **Instalar `xdg-desktop-portal`** com o backend específico do DE:
   ```bash
   sudo dnf install xdg-desktop-portal xdg-desktop-portal-gnome
   # ou para KDE: xdg-desktop-portal-kde
   # ou para sway: xdg-desktop-portal-wlr
   ```
   > **Nota**: o suporte a `portal` para captura de tela ainda não está implementado no código (apenas detectado). A mensagem de erro orienta o fallback para X11.

### Tesseract não encontrado

```bash
which tesseract
# Se vazio:
sudo dnf install tesseract tesseract-langpack-por tesseract-langpack-eng
```

Em Linux, **não** defina `TESSERACT_PATH` no `.env` — deixe vazio para usar do PATH. O Windows usa o caminho default `C:\Program Files\Tesseract-OCR\tesseract.exe`.

### Modelo Whisper (STT) não carrega

```bash
# Verificar cache
ls -la ~/.cache/gravador/audio/whisper/

# Forçar re-download (apague o cache)
rm -rf ~/.cache/gravador/audio/whisper/
python3 scripts/setup_audio_models.py
```

Se o download falhar por rede, baixe manualmente de https://huggingface.co/Systran/faster-whisper-base e coloque em `~/.cache/gravador/audio/whisper/base/`.

### PyAudio não instala no Windows

```powershell
pip install pipwin
pipwin install pyaudio
```

Ou baixe o wheel pré-compilado de https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio.

---

## Como Contribuir

Leia [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
