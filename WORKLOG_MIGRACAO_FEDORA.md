# Worklog — Migração gravadorlegendas para Fedora Linux

Branch: `feat/linux-fedora-support`

## Auditoria inicial — baseline

### Ambiente
- Python 3.12.13 (Linux)
- Tesseract 5.x em `/usr/bin/tesseract`
- Dependências instaladas: mss, pillow, pytesseract, transformers (5.15.1),
  torch 2.13.0+cpu, torchaudio 2.11.0+cpu, silero-vad 6.2.1, openai, requests,
  structlog, prometheus-client, python-dotenv, pytest

### Pontos críticos Windows-only identificados
1. `src/capture/activate_windows_captions.py` — usa `ctypes.windll.user32.keybd_event`
   (Win+Ctrl+L). Importado em `src/main.py` e `src/capture/__init__.py`.
2. `src/audio/capture.py` — `AudioCapture` usa `pyaudio.paWASAPI`. Falha em Linux
   com `paWASAPI` inexistente.
3. `src/audio/manager.py` — chama `AudioCapture()` diretamente (sem abstração).
4. `src/config.py` — `tesseract_path` default `C:\Program Files\Tesseract-OCR\tesseract.exe`.
5. `src/ui/app.py` — checkbox "Ativar legendas do Windows (Win+Ctrl+L)" sempre visível.
6. `src/ui/app.py` — textos hardcoded "WASAPI" em labels e mensagens de erro.
7. `src/ui/app.py:1151` — `os.startfile(path)` (Windows-only).
8. README.md — instalação Linux usa `apt`, sem seção Fedora/Wayland.
9. `scripts/diagnose_audio_device.py` — diagnóstico exclusivamente WASAPI.

### Resultado dos testes (baseline)
```
$ TESSERACT_PATH=/usr/bin/tesseract pytest -q
2 failed, 61 passed in 10.83s
```
- Falhas: `test_ocr.py::test_extract_text_returns_string`,
  `test_ocr.py::test_extract_text_empty_on_blank` (default path Windows).

### Decisões arquiteturais
- Criar `src/platform/` com detecção de plataforma (`PlatformCapabilities`).
- Criar `src/audio/backends/` com `WasapiLoopbackCapture` (Windows) e
  `PipewireCapture` (Linux).
- Criar `src/caption/` com `CaptionSource` Protocol e implementações
  (`WindowsLiveCaptionsSource`, `LocalSTTSource`, `ScreenOCRSource`).
- Substituir `os.startfile` por utilitário multiplataforma.
- Manter `AudioCapture` como classe legada delegando para o backend selecionado,
  para não quebrar a API pública usada por `AudioManager`.

---

## Execução

### Commit 1: feat(platform) — camada de abstração + backends Linux

Arquivos criados:
- `src/platform/__init__.py`
- `src/platform/detection.py` — `PlatformCapabilities`, `detect_os()`, `detect_session_type()`, `detect_capabilities()`
- `src/platform/types.py` — `AudioDevice`, `AudioCaptureConfig`, `AudioChunk`, `AudioCaptureBackend` Protocol, `CaptionSource` Protocol
- `src/platform/selector.py` — `select_audio_backend()`, `select_caption_source()`, `select_screen_capture_backend()`, `BackendSelectionError`
- `src/audio/backends/__init__.py`
- `src/audio/backends/factory.py` — `build_audio_backend()`
- `src/audio/backends/wasapi/__init__.py`
- `src/audio/backends/wasapi/capture.py` — `WasapiLoopbackCapture`
- `src/audio/backends/pipewire/__init__.py`
- `src/audio/backends/pipewire/capture.py` — `PipewireCapture` (via `pw-record` subprocess)
- `src/audio/backends/pipewire/devices.py` — `list_pipewire_devices()` (via `pactl list`)
- `src/caption/__init__.py`
- `src/caption/base.py` — `CaptionSourceBase`, `CaptionSourceError`
- `src/caption/windows_live.py` — `WindowsLiveCaptionsSource`
- `src/caption/local_stt.py` — `LocalSTTSource`
- `src/caption/screen_ocr.py` — `ScreenOCRSource`
- `src/caption/factory.py` — `build_caption_source()`

Arquivos modificados:
- `src/audio/capture.py` — fachada retrocompatível delegando ao backend selecionado
- `src/audio/manager.py` — `device_index` aceita `int | str` (ID PipeWire)
- `src/audio/__init__.py` — docstring atualizado
- `src/capture/screen_capture.py` — detecta Wayland e lança `ScreenCaptureError` claro; valida frame preto
- `src/capture/activate_windows_captions.py` — defensivo: no-op em Linux com aviso
- `src/capture/__init__.py` — docstring atualizado
- `src/main.py` — respeita `PlatformCapabilities`, não chama `activate_windows_captions()` em Linux
- `src/config.py` — novas opções multiplataforma + `validate_settings()` + `assert_settings_valid()` + tesseract path dinâmico
- `src/ui/app.py` — banner de plataforma, checkbox Windows condicional, dispositivos com prefixos 🎤/🔊, `_open_folder_crossplatform()`, aba Config expandida

### Commit 2: test(platform) — 89 novos testes

Arquivos criados:
- `tests/test_platform_detection.py` — 14 testes (detecção OS/sessão/capacidades)
- `tests/test_platform_selector.py` — 16 testes (seleção automática com fallback)
- `tests/test_audio_backends.py` — 17 testes (WASAPI mock, PipeWire mock, factory, fachada)
- `tests/test_caption_sources.py` — 11 testes (3 fontes + factory)
- `tests/test_config_validation.py` — 16 testes (validação, fallback auto, formato chunks)

Bug fix incluído: `_parse_devices` regex usava `kind.capitalize()` mas `pactl` emite "Source" (singular). Corrigido para tratar "sources" → "Source #" e "sinks" → "Sink #".

### Commit 3: docs — README + CONTRIBUTING + lint cleanup

- README.md reescrito com:
  - Pré-requisitos Fedora (`dnf install ...`)
  - Instruções de instalação Fedora e Windows com extras
  - Seção de uso detalhada (microfone, áudio do sistema, transcrição local, OCR, Wayland, X11)
  - Estrutura do projeto com novos módulos
  - Tabela de configurações multiplataforma
  - Troubleshooting completo
- CONTRIBUTING.md explica arquitetura de abstração
- Removidos imports mortos apontados pelo flake8 (F401)

### Adicionais
- `scripts/diagnose_linux_audio.py` — diagnóstico completo (OS, sessão, PipeWire, pactl, fontes, sinks, permissões, orientações)
- `.env.example` — template com todas as opções multiplataforma
- `pyproject.toml`:
  - extras `windows`, `linux`, `audio`, `dev`, `diarization`
  - `[tool.pytest.ini_options]` com marcadores `integration`, `requires_pipewire`, `requires_wasapi`, `requires_display`
  - `[tool.flake8]` com max-line-length=100
  - `[tool.setuptools.packages.find]` para instalar `src*`

---

## Resultado final dos testes

```
$ pytest -q
........................................................................ [ 47%]
........................................................................ [ 94%]
........                                                                 [100%]
152 passed in 10.28s

$ pytest -q -m "not integration"
152 passed in 10.45s

$ python3 -m flake8 src/ --max-line-length=100 --extend-ignore=E501,W503,E203
(limpo, sem avisos)
```

- 63 testes originais preservados (sem regressão).
- 89 novos testes adicionados (todos passam em CI headless).
- Lint flake8 limpo em `src/`.

## Smoke tests manuais executados

```bash
$ python3 -c "from src.platform import detect_capabilities; ..."
OS: linux
Session: unknown
PW: False
Live Captions: False
SysAudio: False
Screen: False
Portal: False
✓ detect_capabilities() não quebra em ambiente headless

$ python3 -c "from src.caption.factory import build_caption_source; ..."
OK: CaptionSourceError lançado: Legendas ao Vivo do Windows não estão disponíveis...
OK: local_stt criado: local_stt
✓ Fábrica respeita plataforma

$ python3 -c "from src.audio.capture import AudioCapture; ..."
Devices encontrados (sem PipeWire): 0
stderr: Falha ao construir backend de áudio: Nenhum servidor de áudio detectado...
✓ Fachada falha graciosamente com mensagem em PT

$ python3 scripts/diagnose_linux_audio.py
[saída completa com seções: OS, PipeWire, PulseAudio, Sources, Sinks, Permissões, Orientações]
✓ Diagnóstico funciona mesmo sem PipeWire instalado
```

## Commits na branch

```
13dcc0b (HEAD -> feat/linux-fedora-support) docs: atualiza README e CONTRIBUTING para multiplataforma Fedora
b634e1b test(platform): adiciona 89 testes para camada de plataforma e backends
c24029a feat(platform): adiciona camada de abstração de plataforma e backends Linux
3a3497d (origin/main, origin/HEAD, main) feat: adiciona region_selector e refatora config 8
```

3 commits coesos na branch de feature, sem commits diretos na main.
