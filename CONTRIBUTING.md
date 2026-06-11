# Contribuindo

Obrigado por considerar contribuir com o Gravador de Legendas!

## Ambiente de Desenvolvimento

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Testes

```bash
pytest tests/ -v
pytest tests/ --cov=src
```

## Lint

```bash
flake8 src/ --max-line-length=88
```

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new translation strategy
fix: correct OCR preprocessing threshold
docs: update README with API examples
refactor: extract noise filter to module
```

## Pull Requests

1. Fork o repositório
2. Crie uma branch: `git checkout -b minha-feature`
3. Faça commits com mensagens claras
4. Rode testes e lint antes de abrir o PR
5. Abra o PR descrevendo as mudanças

## Código de Conduta

Este projeto segue o [Contributor Covenant](CODE_OF_CONDUCT.md).
