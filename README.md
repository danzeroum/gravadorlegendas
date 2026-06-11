# Gravador de Legendas

Captura, traduz e processa legendas da tela em tempo real usando OCR e modelos de tradução locais.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: flake8](https://img.shields.io/badge/code%20style-flake8-000000.svg)](https://github.com/PyCQA/flake8)
[![CI](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml/badge.svg)](https://github.com/danzeroum/gravadorlegendas/actions/workflows/ci.yml)

---

## Funcionalidades

- Captura automática de legendas da tela (região configurável)
- OCR com suporte a múltiplos idiomas (inglês, português, espanhol)
- Tradução local com MarianMT (opus-mt-tc-big-en-pt)
- Fallback para API (OpenAI / DeepSeek) quando necessário
- Detecção de perguntas e sugestão de respostas em Globish
- Resumo automático da reunião via LLM
- Filtro de ruído do OCR com wordlist e heurísticas
- Interface gráfica Tkinter com 4 abas
- Servidor HTTP (FastAPI) para implantação em Docker/VPS

---

## Pré-requisitos

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) instalado no sistema
  - Windows: `choco install tesseract` ou baixe do [site oficial](https://github.com/UB-Mannheim/tesseract/wiki)
  - Linux: `sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng`
- (Opcional) GPU para acelerar modelos de tradução

---

## Instalação

```bash
git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas

# Ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows

# Dependências
pip install -e .

# Configuração
cp .env.example .env
# Edite .env com suas chaves de API se necessário
```

---

## Uso

### Interface Gráfica (Desktop)

```bash
python -m src.main
```

Interface com 4 abas:

| Aba | Função |
|-----|--------|
| Captura | Iniciar/parar gravação, configurar prefixo |
| Tradução | Exibição ao vivo do texto original + traduzido |
| Resumo | Gerar resumo do conteúdo capturado |
| Respostas | Detectar perguntas e gerar respostas Globish |

### Servidor HTTP (Docker)

```bash
docker-compose -f docker/docker-compose.yml up api
```

Endpoints:

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check |
| POST | `/translate` | Tradução de texto |
| POST | `/summarize` | Resumo via LLM |
| POST | `/generate` | Geração de resposta Globish |

---

## Estrutura do Projeto

```
src/
├── capture/                 # Captura de tela (mss) + pré-processamento
│   ├── screen_capture.py
│   └── activate_windows_captions.py
├── ocr/                     # OCR (pytesseract)
│   └── engine.py
├── translation/             # Tradução (Strategy Pattern)
│   ├── base.py              #   Classe abstrata
│   ├── marianmt.py          #   Tradutor local (MarianMT)
│   └── api.py               #   Tradutor via API (OpenAI/DeepSeek)
├── nlp/                     # Processamento de linguagem
│   ├── question_detector.py #   Detecção de perguntas
│   ├── answer_generator.py  #   Geração de respostas Globish
│   └── summarizer.py        #   Resumo de reunião
├── filter/                  # Filtro de ruído do OCR
│   └── noise_filter.py
├── storage/                 # Persistência em arquivo
│   └── file_manager.py
├── ui/                      # Interface gráfica (Tkinter)
│   └── app.py
├── api/                     # Servidor HTTP (FastAPI)
│   └── server.py
├── config.py                # Configuração (.env)
└── main.py                  # Orquestração (SessionManager)

tests/
├── test_capture.py
├── test_ocr.py
├── test_translation.py
├── test_question_detector.py
├── test_noise_filter.py
└── test_file_manager.py

docker/
├── Dockerfile
└── docker-compose.yml
```

---

## Configuração

Variáveis de ambiente (`.env`):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OPENAI_API_KEY` | — | Chave da API OpenAI (para fallback) |
| `DEEPSEEK_API_KEY` | — | Chave da API DeepSeek |
| `TESSERACT_PATH` | `C:\Program Files\...` | Caminho do executável Tesseract |
| `OCR_LANGUAGE` | `eng` | Idioma do OCR |
| `TRANSLATION_MODEL` | `Helsinki-NLP/opus-mt-tc-big-en-pt` | Modelo de tradução |
| `REGION_TOP/LEFT/WIDTH/HEIGHT` | `0,50,1820,80` | Região de captura |

---

## Testes

```bash
pytest tests/ -v           # Todos os testes
pytest tests/ --cov=src    # Com cobertura
flake8 src/                # Lint
```

---

## Como Contribuir

Leia [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
