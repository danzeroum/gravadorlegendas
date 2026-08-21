"""Tokens visuais centralizados da interface.

Regras deste módulo:

- Toda cor é uma tupla ``(light, dark)`` — nunca um hex solto — para que
  o contraste seja verificável nos dois temas.
- Nenhum texto funcional abaixo de ``FONT_LABEL_SIZE`` (13 px).
- A escala de usuário alimenta SOMENTE ``ctk.set_widget_scaling``.
  ``set_window_scaling`` permanece em ``WINDOW_SCALING = 1.0`` para
  evitar escala dupla em cascata (janela × widgets) no Linux.
- ``apply_widget_scaling`` deve ser chamada ANTES de criar ``ctk.CTk()``;
  mudanças de escala persistidas exigem reinício da UI.
"""
from __future__ import annotations

import os
from typing import Mapping

import customtkinter as ctk

# --- Tipografia -----------------------------------------------------------
# "Sans Serif"/"Monospace" são famílias genéricas que o Tk resolve via
# fontconfig no Fedora — não dependem de uma fonte empacotada (ex.: Inter).
FONT_FAMILY = "Sans Serif"
FONT_FAMILY_MONO = "Monospace"

FONT_TITLE_SIZE = 22
FONT_HEADING_SIZE = 18
FONT_BODY_SIZE = 15
FONT_LABEL_SIZE = 13
FONT_BUTTON_SIZE = 14

# --- Dimensões ---
BUTTON_HEIGHT = 40
BUTTON_HEIGHT_PRIMARY = 44
BUTTON_WIDTH_SMALL = 96

PAD_SM = 8
PAD_MD = 12
PAD_LG = 20

RESULTS_PANEL_WIDTH = 420

# --- Escala DPI -----------------------------------------------------------
WINDOW_SCALING = 1.0  # fixo: fator de usuário nunca vai para a janela
DEFAULT_WIDGET_SCALING = 1.0
MIN_WIDGET_SCALING = 0.9
MAX_WIDGET_SCALING = 1.4
WIDGET_SCALING_ENV = "APP_WIDGET_SCALING"

# Opções exibidas no seletor de escala (rótulo → fator)
SCALING_OPTIONS: dict[str, float] = {
    "90%": 0.9,
    "100%": 1.0,
    "110%": 1.1,
    "125%": 1.25,
    "140%": 1.4,
}


def _to_float(value) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def resolve_widget_scaling(
    env: Mapping[str, str] | None = None,
    stored: float | str | None = None,
) -> float:
    """Resolve o fator de escala de widgets.

    Precedência: ``APP_WIDGET_SCALING`` (env) > valor persistido > default.
    O resultado é limitado a [MIN_WIDGET_SCALING, MAX_WIDGET_SCALING].
    """
    env = os.environ if env is None else env
    factor = _to_float(env.get(WIDGET_SCALING_ENV))
    if factor is None:
        factor = _to_float(stored)
    if factor is None:
        factor = DEFAULT_WIDGET_SCALING
    return min(MAX_WIDGET_SCALING, max(MIN_WIDGET_SCALING, factor))


def apply_widget_scaling(factor: float) -> None:
    """Aplica a escala ANTES de criar ``CTk()``. Janela permanece 1.0."""
    ctk.set_widget_scaling(factor)
    ctk.set_window_scaling(WINDOW_SCALING)


def scaling_label(factor: float) -> str:
    """Retorna o rótulo de SCALING_OPTIONS mais próximo do fator."""
    return min(SCALING_OPTIONS, key=lambda lbl: abs(SCALING_OPTIONS[lbl] - factor))


class Theme:
    """Tokens de cor (tuplas light/dark) e fábricas de fonte."""

    # Superfícies
    BG = ("#F3F4F6", "#111827")
    SURFACE = ("#FFFFFF", "#1F2937")
    SURFACE_ELEVATED = ("#F9FAFB", "#273449")
    BORDER = ("#D1D5DB", "#374151")

    # Texto — TEXT_MUTED mantém contraste >= 4.5:1 sobre SURFACE (claro)
    TEXT = ("#111827", "#F9FAFB")
    TEXT_MUTED = ("#4B5563", "#9CA3AF")

    # Ações
    PRIMARY = ("#2563EB", "#3B82F6")
    PRIMARY_HOVER = ("#1D4ED8", "#2563EB")
    SUCCESS = ("#15803D", "#16A34A")
    SUCCESS_HOVER = ("#166534", "#15803D")
    DANGER = ("#B91C1C", "#DC2626")
    DANGER_HOVER = ("#991B1B", "#B91C1C")
    WARNING = ("#B45309", "#D97706")
    FOCUS = ("#2563EB", "#60A5FA")

    # Toasts / banner
    TOAST_OK_BG = ("#DCFCE7", "#14532D")
    TOAST_OK_TEXT = ("#14532D", "#DCFCE7")
    TOAST_WARN_BG = ("#FEF3C7", "#78350F")
    TOAST_WARN_TEXT = ("#78350F", "#FEF3C7")
    TOAST_ERROR_BG = ("#FEE2E2", "#7F1D1D")
    TOAST_ERROR_TEXT = ("#7F1D1D", "#FEE2E2")

    @staticmethod
    def title() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_TITLE_SIZE, weight="bold")

    @staticmethod
    def heading() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_HEADING_SIZE, weight="bold")

    @staticmethod
    def body() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY_SIZE)

    @staticmethod
    def label() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_LABEL_SIZE)

    @staticmethod
    def label_bold() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_LABEL_SIZE, weight="bold")

    @staticmethod
    def button() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY, size=FONT_BUTTON_SIZE, weight="bold")

    @staticmethod
    def mono() -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT_FAMILY_MONO, size=FONT_LABEL_SIZE)


def install_focus_ring(widget) -> None:
    """Realce de foco por teclado: borda na cor FOCUS ao receber foco.

    Aplicável a widgets CTk com ``border_width``/``border_color``
    (CTkEntry, CTkOptionMenu, CTkButton, CTkTextbox). Falha silenciosa
    em widgets sem suporte a borda.
    """
    try:
        original_width = widget.cget("border_width")
        original_color = widget.cget("border_color")
    except (ValueError, TypeError):
        return

    def _on_focus_in(_event):
        widget.configure(border_width=2, border_color=Theme.FOCUS)

    def _on_focus_out(_event):
        widget.configure(border_width=original_width, border_color=original_color)

    widget.bind("<FocusIn>", _on_focus_in, add="+")
    widget.bind("<FocusOut>", _on_focus_out, add="+")
