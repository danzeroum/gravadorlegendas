"""Painel central de transcrição ao vivo com ações no cabeçalho."""
import customtkinter as ctk
from src.ui.theme import (
    Theme, BUTTON_HEIGHT, BUTTON_WIDTH_SMALL,
    PAD_SM, PAD_MD, PAD_LG, install_focus_ring,
)
from src.ui.components.tooltip import Tooltip


PLACEHOLDER_TEXT = (
    "A transcrição aparecerá aqui quando a captura for iniciada.\n"
    "Use Ctrl+R ou o botão \"Iniciar transcrição\"."
)


class TranscriptionPanel(ctk.CTkFrame):
    def __init__(
        self, master,
        on_copy, on_save, on_export, on_clear,
    ):
        super().__init__(master, corner_radius=0, fg_color=Theme.SURFACE)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._placeholder_active = True

        # Cabeçalho: título + ações
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_MD, 0))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="Transcrição ao vivo",
            font=Theme.heading(), text_color=Theme.TEXT,
        ).grid(row=0, column=0, padx=0, sticky="w")

        # Botões de ação (todos altura BUTTON_HEIGHT, largura automática)
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e")

        self._btn_copy = ctk.CTkButton(
            btn_frame, text="Copiar", width=BUTTON_WIDTH_SMALL, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=lambda: on_copy(self.get_text()),
            state="disabled",
        )
        self._btn_copy.grid(row=0, column=0, padx=PAD_SM)
        install_focus_ring(self._btn_copy)
        Tooltip(self._btn_copy, "Copiar transcrição (Ctrl+C)")

        self._btn_save = ctk.CTkButton(
            btn_frame, text="Salvar .txt", width=BUTTON_WIDTH_SMALL, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=lambda: on_save(self.get_text()),
            state="disabled",
        )
        self._btn_save.grid(row=0, column=1, padx=PAD_SM)
        install_focus_ring(self._btn_save)
        Tooltip(self._btn_save, "Salvar transcrição como .txt (Ctrl+S)")

        self._btn_export = ctk.CTkButton(
            btn_frame, text="Exportar .md", width=BUTTON_WIDTH_SMALL, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=on_export,
            state="disabled",
        )
        self._btn_export.grid(row=0, column=2, padx=PAD_SM)
        install_focus_ring(self._btn_export)
        Tooltip(self._btn_export, "Exportar transcrição como Markdown com falantes")

        self._btn_clear = ctk.CTkButton(
            btn_frame, text="Limpar", width=BUTTON_WIDTH_SMALL, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=lambda: on_clear(self),
            state="disabled",
        )
        self._btn_clear.grid(row=0, column=3, padx=PAD_SM)
        install_focus_ring(self._btn_clear)
        Tooltip(self._btn_clear, "Limpar transcrição (Ctrl+L)")

        # Área de texto
        self._textbox = ctk.CTkTextbox(
            self, wrap="word", font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
        )
        self._textbox.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=PAD_MD)
        self._show_placeholder()

    # --- Helpers de placeholder ----------------------------------------------

    def _show_placeholder(self) -> None:
        self._placeholder_active = True
        self._textbox.configure(state="normal", text_color=Theme.TEXT_MUTED)
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", PLACEHOLDER_TEXT)
        self._textbox.configure(state="disabled")
        self._update_actions_state(False, False)

    def _hide_placeholder(self) -> None:
        if self._placeholder_active:
            self._placeholder_active = False
            self._textbox.configure(state="normal", text_color=Theme.TEXT)
            self._textbox.delete("1.0", "end")

    # --- API pública ----------------------------------------------------------

    def append_line(self, line: str) -> None:
        self._hide_placeholder()
        self._textbox.configure(state="normal")
        self._textbox.insert("end", line + "\n")
        self._textbox.see("end")
        self._textbox.configure(state="disabled")
        self._update_actions_state(True, True)

    def get_text(self) -> str:
        if self._placeholder_active:
            return ""
        self._textbox.configure(state="normal")
        text = self._textbox.get("1.0", "end").rstrip()
        self._textbox.configure(state="disabled")
        return text

    def has_content(self) -> bool:
        return not self._placeholder_active and bool(self._textbox.get("1.0", "end").strip())

    def clear(self) -> None:
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
        self._show_placeholder()

    def set_export_enabled(self, enabled: bool) -> None:
        self._btn_export.configure(state="normal" if enabled else "disabled")

    def _update_actions_state(self, has_content: bool, can_export: bool = False) -> None:
        state = "normal" if has_content else "disabled"
        self._btn_copy.configure(state=state)
        self._btn_save.configure(state=state)
        self._btn_clear.configure(state=state)
        self._btn_export.configure(state="normal" if can_export else "disabled")
