"""Mapa único de atalhos de teclado (bind → ação).

Fonte de verdade para app.py, tooltips e README.
"""
from __future__ import annotations

SHORTCUTS: dict[str, str] = {
    "<Control-r>": "toggle_recording",
    "<Control-s>": "save_transcription",
    "<Control-l>": "clear_transcription",
    "<Control-comma>": "open_settings",
    "<Escape>": "close_secondary",
}

SHORTCUT_LABELS: dict[str, str] = {
    "toggle_recording": "Ctrl+R — Iniciar/parar gravação",
    "save_transcription": "Ctrl+S — Salvar transcrição",
    "clear_transcription": "Ctrl+L — Limpar transcrição",
    "open_settings": "Ctrl+, — Abrir configurações",
    "close_secondary": "Esc — Fechar painel/diálogo",
}
