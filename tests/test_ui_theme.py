"""Testes headless para tokens de tema (src/ui/theme.py).

Não instanciam CTk/TTK — apenas validam constantes e funções puras.
"""
from __future__ import annotations

import sys

import pytest


# Importa o módulo (pode falhar se customtkinter não tiver display, mas import OK)
from src.ui import theme as theme_module


class TestThemeConstants:
    """Valida mínimos de acessibilidade nos tamanhos de fonte."""

    def test_font_sizes_minimums(self):
        assert theme_module.FONT_LABEL_SIZE >= 13
        assert theme_module.FONT_BODY_SIZE >= 15
        assert theme_module.FONT_BUTTON_SIZE >= 14
        assert theme_module.FONT_HEADING_SIZE >= 18
        assert theme_module.FONT_TITLE_SIZE >= 22

    def test_button_heights(self):
        assert theme_module.BUTTON_HEIGHT >= 40
        assert theme_module.BUTTON_HEIGHT_PRIMARY >= 44

    def test_color_tuples(self):
        """Todas as cores devem ser tuplas (light, dark) de strings hex."""
        import src.ui.theme as t
        for name in dir(t.Theme):
            if name.isupper() and not name.startswith("_"):
                val = getattr(t.Theme, name)
                if isinstance(val, tuple):
                    assert len(val) == 2, f"{name} deve ser tupla de 2"
                    for v in val:
                        assert isinstance(v, str) and v.startswith("#"), f"{name} item {v!r} deve ser hex"

    def test_windows_scaling_constant(self):
        assert theme_module.WINDOW_SCALING == 1.0

    def test_scaling_options(self):
        assert theme_module.SCALING_OPTIONS["100%"] == 1.0
        assert 0.9 in theme_module.SCALING_OPTIONS.values()
        assert 1.4 in theme_module.SCALING_OPTIONS.values()


class TestResolveWidgetScaling:
    """Função pura resolve_widget_scaling: env > stored > default, clamp."""

    def test_env_precedence(self):
        factor = theme_module.resolve_widget_scaling(env={"APP_WIDGET_SCALING": "1.25"}, stored=1.1)
        assert factor == 1.25

    def test_stored_fallback(self):
        factor = theme_module.resolve_widget_scaling(env={}, stored=1.15)
        assert factor == 1.15

    def test_default(self):
        factor = theme_module.resolve_widget_scaling(env={}, stored=None)
        assert factor == theme_module.DEFAULT_WIDGET_SCALING

    def test_clamp_min(self):
        factor = theme_module.resolve_widget_scaling(env={"APP_WIDGET_SCALING": "0.5"}, stored=None)
        assert factor == theme_module.MIN_WIDGET_SCALING

    def test_clamp_max(self):
        factor = theme_module.resolve_widget_scaling(env={"APP_WIDGET_SCALING": "2.0"}, stored=None)
        assert factor == theme_module.MAX_WIDGET_SCALING

    def test_invalid_env_ignored(self):
        factor = theme_module.resolve_widget_scaling(env={"APP_WIDGET_SCALING": "abc"}, stored=1.1)
        assert factor == 1.1


class TestScalingLabel:
    def test_returns_closest_label(self):
        assert theme_module.scaling_label(1.0) == "100%"
        assert theme_module.scaling_label(1.12) == "110%"
        assert theme_module.scaling_label(1.2) == "125%"
        # 0.95 está equidistante de 0.9 e 1.0; min() pega o primeiro
        assert theme_module.scaling_label(0.95) in ("90%", "100%")