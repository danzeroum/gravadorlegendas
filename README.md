# Gravador de Reunião

Captura, transcreve, traduz e processa legendas da tela em tempo real com OCR, captura de áudio, diarização de falantes e LLM local.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: flake8](https://img.shields.io/badge/code%20style-flake8-000000.svg)](https://github.com/PyCQA/flake8)
[![tests](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml/badge.svg)](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml)

---

## Funcionalidades

- **Captura de tela** — região configurável, OCR com suporte a múltiplos idiomas (inglês, português, espanhol)
- **Tradução local** — MarianMT (opus-mt-tc-big-en-pt) com fallback para API (OpenAI / DeepSeek)
- **Áudio ao vivo** — captura WASAPI loopback, transcrição com faster-whisper, VAD (silero-vad)
- **Diarização** — identificação de falantes em tempo real ou offline (diart + pyannote.audio)
- **Exportação** — transcrição com rótulos de falante em Markdown
- **LLM pluggável** — Ollama (Basic Auth + NDJSON), OpenAI, DeepSeek, LocalGGUF
- **Resumo automático** da reunião via LLM, incluindo contexto de áudio + OCR
- **Detecção de perguntas** e sugestão de respostas em Globish
- **Filtro de ruído** do OCR com wordlist e heurísticas
- **Interface gráfica** CustomTkinter com 7 abas
- **Servidor HTTP** (FastAPI) para implantação em Docker/VPS

---

## Pré-requisitos

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) instalado no sistema
  - Windows: `choco install tesseract` ou [site oficial](https://github.com/UB-Mannheim/tesseract/wiki)
  - Linux: `sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng`
- (Opcional) GPU NVIDIA com CUDA para acelerar faster-whisper
- (Opcional) Conta [Hugging Face](https://huggingface.co) com token aceito para `pyannote/speaker-diarization-3.1`

---

## Instalação

```bash
git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas

# Ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows

# Dependências base (OCR, tradução, LLM)
pip install -e .

# Com suporte a áudio (transcrição + diarização)
pip install -e ".[audio]"

# Ou instalar apenas os requisitos de áudio manualmente
pip install -r requirements/audio.txt

# Configuração
cp .env.example .env
# Edite .env com suas chaves de API e credenciais
```

### Diarização (opcional)

Para identificação de falantes, instale dependências extras e aceite os termos da HF:

```bash
pip install diart pyannote.audio

# Faça login na Hugging Face e aceite os termos em:
# https://huggingface.co/pyannote/speaker-diarization-3.1
huggingface-cli login
```

---

## Uso

### Interface Gráfica (Desktop)

```bash
python -m src.main
```

| Aba | Função |
|-----|--------|
| Tradução | Exibição ao vivo do texto original + traduzido |
| Captura | Iniciar/parar captura de tela, configurar prefixo |
| Áudio | Iniciar/parar captura de áudio, transcrição ao vivo, diarização, exportar |
| Resumo | Gerar resumo do conteúdo capturado (OCR + áudio) |
| Respostas | Detectar perguntas e gerar respostas Globish |
| IA | Configurar provider LLM ativo (Ollama, OpenAI, DeepSeek, LocalGGUF) |
| Config | Tema, região de captura, atalhos |

#### Atalhos de teclado

| Atalho | Ação |
|--------|------|
| `Ctrl+I` | Abrir aba IA |
| `Ctrl+P` | Abrir aba Captura |
| `Ctrl+R` | Abrir aba Resumo |
| `Ctrl+S` | Abrir aba Respostas |
| `Ctrl+E` | Alternar tema |

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
├── audio/                   # Captura e processamento de áudio
│   ├── capture.py           #   WASAPI loopback (PyAudio)
│   ├── vad.py               #   Voice Activity Detection (silero-vad)
│   ├── buffer.py            #   Buffer circular thread-safe
│   ├── transcribe.py        #   Transcrição (faster-whisper em Process)
│   ├── diarize.py           #   Diarização de falantes (diart)
│   ├── manager.py           #   Orquestração com 2 filas + merge
│   ├── metrics.py           #   Latência e sobreposição
│   └── models.py            #   Download/cache de modelos
├── capture/                 # Captura de tela (mss) + pré-processamento
├── ocr/                     # OCR (pytesseract)
├── translation/             # Tradução (Strategy Pattern)
├── nlp/                     # Processamento de linguagem
├── filter/                  # Filtro de ruído do OCR
├── llm/                     # Sistema de LLM pluggável
│   ├── base.py              #   Provider ABC
│   ├── registry.py          #   ProviderRegistry singleton
│   ├── manager.py           #   LLMManager singleton
│   └── providers/           #   Implementações
│       ├── openai.py
│       ├── deepseek.py
│       ├── ollama.py        #   Basic Auth + NDJSON
│       └── local_gguf.py    #   CPU-only, opcional
├── storage/                 # Persistência em arquivo
├── ui/                      # Interface CustomTkinter
│   └── app.py               #   7 abas, tema, atalhos
├── api/                     # Servidor HTTP (FastAPI)
├── config.py                # Configuração (.env)
├── config_store.py          # Config JSON (LLM, speaker_map)
└── main.py                  # Orquestração (SessionManager)

tests/                       # 63 testes — pytest
├── test_audio_buffer.py
├── test_audio_metrics.py
├── test_audio_vad.py
├── test_audio_manager.py
├── test_audio_diarize.py
└── ...
```

---

## Configuração

Variáveis de ambiente (`.env`):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OPENAI_API_KEY` | — | Chave da API OpenAI |
| `DEEPSEEK_API_KEY` | — | Chave da API DeepSeek |
| `OLLAMA_BASE_URL` | `https://api.buildtovalue.cloud` | URL do servidor Ollama |
| `OLLAMA_USERNAME` | — | Usuário Basic Auth |
| `OLLAMA_PASSWORD` | — | Senha Basic Auth |
| `OLLAMA_MODEL` | `mistral:latest` | Modelo Ollama |
| `TESSERACT_PATH` | `C:\Program Files\...` | Caminho do Tesseract |
| `OCR_LANGUAGE` | `eng` | Idioma do OCR |
| `TRANSLATION_MODEL` | `Helsinki-NLP/opus-mt-tc-big-en-pt` | Modelo de tradução |
| `REGION_TOP/LEFT/WIDTH/HEIGHT` | `0,50,1820,80` | Região de captura |

---

## Testes

```bash
pytest tests/ -v                # 63 testes
pytest tests/ --cov=src         # Com cobertura
flake8 src/ --max-line-length=100
```

---

## Como Contribuir

Leia [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
