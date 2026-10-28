#!/usr/bin/env bash
# Prepara o ambiente para transcrever áudios (uso pelo opencode ou manual).
#
#   bash scripts/setup_ambiente.sh                         # transcrição
#   bash scripts/setup_ambiente.sh --separar-participantes # + separação de vozes
#
# Cria .venv (se não existir), instala o pacote com o extra de áudio e, com
# --separar-participantes, o extra de diarização (pyannote.audio). Idempotente.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "→ Criando ambiente virtual .venv"
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade --quiet pip

EXTRAS="audio"
if [ "${1:-}" = "--separar-participantes" ]; then
  EXTRAS="audio,diarization"
fi
echo "→ Instalando dependências (.[${EXTRAS}]) — pode demorar na primeira vez"
.venv/bin/python -m pip install --quiet -e ".[${EXTRAS}]"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "→ .env criado a partir de .env.example"
fi
mkdir -p audios/transcricoes

echo
.venv/bin/python scripts/transcrever_audio.py --verificar || true
