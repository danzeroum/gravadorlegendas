"""Cabeçalho da janela: título, status, botões de tema e configurações."""
import customtkinter as ctk
from src.ui.theme import (
    Theme, BUTTON_HEIGHT, BUTTON_WIDTH_SMALL,
    PAD_SM, PAD_MD, PAD_LG, install_focus_ring,
)
from src.ui.components.tooltip import Tooltip


class Header(ctk.CTkFrame):
    def __init__(self, master, on_toggle_theme, on_open_settings):
        super().__init__(master, corner_radius=0, fg_color=Theme.SURFACE)
        self.grid_columnconfigure(1, weight=1)

        # Título
        ctk.CTkLabel(
            self, text="Gravador de Legendas",
            font=Theme.title(), text_color=Theme.TEXT,
        ).grid(row=0, column=0, padx=PAD_LG, pady=PAD_SM, sticky="w")

        # Status pill (coluna 1 — expansível, alinhado à direita)
        self._status_lbl = ctk.CTkLabel(
            self, text="● Pronto",
            font=Theme.label_bold(), text_color=Theme.TEXT_MUTED,
        )
        self._status_lbl.grid(row=0, column=1, padx=PAD_MD, pady=PAD_SM, sticky="e")

        # Botão tema
        self._theme_btn = ctk.CTkButton(
            self, text="☀️ Claro", width=BUTTON_WIDTH_SMALL,
            height=BUTTON_HEIGHT, font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=on_toggle_theme,
        )
        self._theme_btn.grid(row=0, column=2, padx=PAD_SM, pady=PAD_SM)
        install_focus_ring(self._theme_btn)
        Tooltip(self._theme_btn, "Alternar tema claro/escuro")

        # Botão configurações
        self._settings_btn = ctk.CTkButton(
            self, text="⚙ Configurações", width=160,
            height=BUTTON_HEIGHT, font=Theme.button(),
            fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=on_open_settings,
        )
        self._settings_btn.grid(row=0, column=3, padx=PAD_SM, pady=PAD_SM, sticky="e")
        install_focus_ring(self._settings_btn)
        Tooltip(self._settings_btn, "Abrir configurações (Ctrl+,)")

    def set_status(self, text: str, kind: str = "idle") -> None:
        color_map = {
            "idle": Theme.TEXT_MUTED,
            "recording": Theme.SUCCESS,
            "busy": Theme.WARNING,
            "error": Theme.DANGER,
        }
        self._status_lbl.configure(text=text, text_color=color_map.get(kind, Theme.TEXT_MUTED))

    def set_theme_label(self, is_dark: bool) -> None:
        self._theme_btn.configure(text="🌙 Escuro" if is_dark else "☀️ Claro")
