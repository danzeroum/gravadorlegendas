#!/bin/bash
# Script para iniciar o Gravador de Legendas

cd /home/danzeroum/work/products/personal/gravadorlegendas

# Ativa ambiente virtual
source .venv/bin/activate

# Variáveis de diagnóstico opcional (descomente para debug)
# export APP_UI_DIAGNOSTICS=1
# export APP_WIDGET_SCALING=2.0

echo "Iniciando Gravador de Legendas..."
echo "Pressione Ctrl+C no terminal para fechar"

# Inicia a aplicação
python -m src.main