# Contribuindo

Obrigado por considerar contribuir com o Gravador de Legendas!

## Ambiente de Desenvolvimento

### Fedora Linux

```bash
sudo dnf install -y \
  python3 python3-pip python3-tkinter \
  tesseract tesseract-langpack-por tesseract-langpack-eng \
  pipewire pipewire-utils pipewire-pulseaudio \
  gcc gcc-c++ make

git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[linux,audio,dev]"
```

### Windows

```powershell
git clone https://github.com/danzeroum/gravadorlegendas.git
cd gravadorlegendas
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[windows,audio,dev]"
```

## Arquitetura Multiplataforma

O projeto usa uma **camada de abstração de plataforma** em `src/platform/`.
Toda decisão sobre qual backend usar passa por lá. **Nunca** chame APIs
Windows diretamente fora de `src/audio/backends/wasapi/` ou
`src/caption/windows_live.py`.

```text
src/platform/
├── detection.py   # PlatformCapabilities (OS, sessão, capacidades)
├── selector.py    # select_audio_backend(), select_caption_source(), ...
└── types.py       # AudioCaptureBackend Protocol, AudioDevice, ...
```

Para adicionar um novo backend:

1. Crie `src/audio/backends/<nome>/` implementando `AudioCaptureBackend`.
2. Adicione a opção em `VALID_AUDIO_BACKENDS` em `src/platform/selector.py`.
3. Adicione o caso em `build_audio_backend()` em `src/audio/backends/factory.py`.
4. Escreva testes em `tests/test_audio_backends.py` com mocks.

Para adicionar uma nova fonte de legenda:

1. Crie `src/caption/<nome>.py` herde de `CaptionSourceBase`.
2. Adicione em `VALID_CAPTION_SOURCES` em `src/platform/selector.py`.
3. Adicione o caso em `build_caption_source()` em `src/caption/factory.py`.
4. Escreva testes em `tests/test_caption_sources.py`.

## Testes

```bash
# Todos os testes unitários (sem hardware, sem rede, sem GPU)
pytest -q

# Excluir integração
pytest -m "not integration"

# Com cobertura
pytest tests/ --cov=src

# Apenas nova camada de plataforma
pytest tests/test_platform_detection.py tests/test_platform_selector.py -v
```

**Regras para novos testes**:

- Testes unitários **não** podem exigir hardware real, PipeWire rodando, Windows, GPU, download de modelos ou rede.
- Se o teste exigir qualquer um desses, marque com `@pytest.mark.integration` (e um dos marcadores específicos: `requires_pipewire`, `requires_wasapi`, `requires_display`).
- Use mocks para simular `sys.platform`, `os.environ`, e módulos externos.

## Lint

```bash
flake8 src/ --max-line-length=100
# Configuração em pyproject.toml [tool.flake8]
```

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(platform): add new audio backend for FreeBSD
fix(pipewire): handle pw-record EOF gracefully
docs: update README with FreeBSD instructions
refactor(caption): extract ScreenOCRSource to its own module
test(config): add validation tests for audio_source
```

## Pull Requests

1. Fork o repositório
2. Crie uma branch: `git checkout -b feat/minha-feature`
3. Faça commits pequenos e coesos
4. Rode `pytest -q` e `flake8 src/` antes de abrir o PR
5. Verifique se a UI funciona em ambas as plataformas quando aplicável
6. Abra o PR descrevendo as mudanças e como testou

## Código de Conduta

Este projeto segue o [Contributor Covenant](CODE_OF_CONDUCT.md).
