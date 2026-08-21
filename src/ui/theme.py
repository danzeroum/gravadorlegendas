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
- Em Linux, detectamos a escala do display (Xft.dpi / gsettings) e
  a multiplicamos pela escolha do usuário para corrigir legibilidade em
  Wayland/HiDPI.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Mapping

import customtkinter as ctk

from src.config_store import config_store

# --- Escala DPI (definida antes da escala base Linux) ---------------------
WINDOW_SCALING = 1.0  # fixo: fator de usuário nunca vai para a janela
DEFAULT_WIDGET_SCALING = 1.25
MIN_WIDGET_SCALING = 0.9
MAX_WIDGET_SCALING = 3.0
WIDGET_SCALING_ENV = "APP_WIDGET_SCALING"


def _to_float(value) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def detect_display_scale() -> float:
    """Detecta a escala do display no Linux via Xft.dpi ou gsettings.

    Em Wayland/HiDPI, Xft.dpi reflete o produto entre escala de display e
    fator de texto (ex.: 96 * 2.0 * 1.21 = 232). Retorna 1.0 em Windows,
    macOS ou se a detecção falhar.

    XWayland costuma reportar 96 DPI mesmo em telas 2x, então quando Xft.dpi
    é 96 (ou inexistente) usamos 2.0 como fallback para garantir legibilidade.
    """
    if not sys.platform.startswith("linux"):
        return 1.0

    # 1. Xft.dpi via xrdb (presente na maioria dos desktops X11/Wayland)
    try:
        result = subprocess.run(
            ["xrdb", "-query"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        for line in result.stdout.splitlines():
            if "xft.dpi" in line.lower():
                parts = line.split(":", 1)
                if len(parts) == 2:
                    dpi = _to_float(parts[1].strip())
                    if dpi and dpi > 96:
                        # DPI real > 96 (ex.: 116, 192, 232)
                        return max(1.0, dpi / 96.0)
    except Exception:
        pass

    # 2. Fallback: gsettings do GNOME (text-scaling-factor)
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "text-scaling-factor"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        factor = _to_float(result.stdout.strip())
        if factor and factor > 1.0:
            # XWayland em telas HiDPI: text-scale sozinho nao compensa a escala 2x
            return max(2.0, factor)
    except Exception:
        pass

    # 3. XWayland em telas HiDPI nao expoe a escala real; assume 2.0
    return 2.0


# --- Escala base Linux/Wayland --------------------------------------------
# Aplicacoes X11 via XWayland nao sao escaladas pelo compositor. Sem ajuste,
# fontes e widgets ficam minusculos em telas HiDPI.
# A escala total = display_scale * ui_scaling (limitada a MAX_WIDGET_SCALING).
# O usuario pode ajustar via Configuracoes -> Aparencia (requer reinicio)
# ou APP_WIDGET_SCALING env.
if sys.platform.startswith("linux"):
    try:
        _env_scale = float(os.environ.get(WIDGET_SCALING_ENV, ""))
        _env_scale = max(MIN_WIDGET_SCALING, min(MAX_WIDGET_SCALING, _env_scale))
    except ValueError:
        _env_scale = 0.0

    if _env_scale > 0:
        _LINUX_SCALE = _env_scale
    else:
        _display_scale = detect_display_scale()
        _user_scale = config_store.get("ui_scaling", 1.0)
        _LINUX_SCALE = min(
            MAX_WIDGET_SCALING,
            max(MIN_WIDGET_SCALING, _display_scale * _user_scale),
        )
else:
    _LINUX_SCALE = 1.0

# --- Tipografia (valores base, o customtkinter escala via widget_scaling) ---
FONT_FAMILY = "Sans Serif"
FONT_FAMILY_MONO = "Monospace"

FONT_TITLE_SIZE = 26
FONT_HEADING_SIZE = 22
FONT_BODY_SIZE = 18
FONT_LABEL_SIZE = 16
FONT_BUTTON_SIZE = 16

# --- Dimensões (valores base) ---
BUTTON_HEIGHT = 44
BUTTON_HEIGHT_PRIMARY = 48
BUTTON_WIDTH_SMALL = 96

PAD_SM = 10
PAD_MD = 14
PAD_LG = 20

RESULTS_PANEL_WIDTH = 420

# Opções exibidas no seletor de escala (rótulo → fator)
SCALING_OPTIONS: dict[str, float] = {
    "90%": 0.9,
    "100%": 1.0,
    "110%": 1.1,
    "125%": 1.25,
    "150%": 1.5,
    "175%": 1.75,
    "200%": 2.0,
    "250%": 2.5,
    "300%": 3.0,
}


def detect_display_scale() -> float:
    """Detecta a escala do display no Linux via Xft.dpi ou gsettings.

    Em Wayland/HiDPI, Xft.dpi reflete o produto entre escala de display e
    fator de texto (ex.: 96 * 2.0 * 1.21 = 232). Retorna 1.0 em Windows,
    macOS ou se a detecção falhar.

    XWayland costuma reportar 96 DPI mesmo em telas 2x, então quando Xft.dpi
    é 96 (ou inexistente) usamos 2.0 como fallback para garantir legibilidade.
    """
    if not sys.platform.startswith("linux"):
        return 1.0

    # 1. Xft.dpi via xrdb (presente na maioria dos desktops X11/Wayland)
    try:
        result = subprocess.run(
            ["xrdb", "-query"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        for line in result.stdout.splitlines():
            if "xft.dpi" in line.lower():
                parts = line.split(":", 1)
                if len(parts) == 2:
                    dpi = _to_float(parts[1].strip())
                    if dpi and dpi > 96:
                        # DPI real > 96 (ex.: 116, 192, 232)
                        return max(1.0, dpi / 96.0)
    except Exception:
        pass

    # 2. Fallback: gsettings do GNOME (text-scaling-factor)
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "text-scaling-factor"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        factor = _to_float(result.stdout.strip())
        if factor and factor > 1.0:
            # XWayland em telas HiDPI: text-scale sozinho nao compensa a escala 2x
            return max(2.0, factor)
    except Exception:
        pass

    # 3. XWayland em telas HiDPI nao expoe a escala real; assume 2.0
    return 2.0


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
    """Aplica a escala ANTES de criar ``CTk()``.

    Em Linux/HiDPI usa _LINUX_SCALE para widgets e janela, mantendo
    proporcoes corretas. Em Windows o sistema gerencia HiDPI e usamos
    apenas o widget_scaling com janela em 1.0.
    """
    if sys.platform.startswith("linux"):
        ctk.set_widget_scaling(_LINUX_SCALE)
        ctk.set_window_scaling(_LINUX_SCALE)
    else:
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
