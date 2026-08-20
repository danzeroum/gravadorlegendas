"""Barra de status inferior: origem/dispositivo/modelo + arquivo atual + abrir pasta."""
import customtkinter as ctk
from src.ui.theme import Theme, BUTTON_HEIGHT, BUTTON_WIDTH_SMALL, PAD_SM, PAD_MD, PAD_LG, install_focus_ring
from src.ui.components.tooltip import Tooltip


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, on_open_folder):
        super().__init__(master, corner_radius=0, fg_color=Theme.SURFACE)
        self.grid_columnconfigure(0, weight=1)

        # Esquerda: origem/dispositivo/modelo
        self._source_lbl = ctk.CTkLabel(
            self, text="Origem: —  •  Modelo: —  •  Backend: —",
            font=Theme.label(), text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self._source_lbl.grid(row=0, column=0, padx=PAD_LG, pady=PAD_SM, sticky="w")

        # Direita: arquivo + botão
        self._file_lbl = ctk.CTkLabel(
            self, text="Nenhum arquivo",
            font=Theme.label(), text_color=Theme.TEXT_MUTED,
            anchor="e",
        )
        self._file_lbl.grid(row=0, column=1, padx=PAD_LG, pady=PAD_SM, sticky="e")

        self._open_folder_btn = ctk.CTkButton(
            self, text="📂 Abrir Pasta", width=BUTTON_WIDTH_SMALL, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=on_open_folder,
        )
        self._open_folder_btn.grid(row=0, column=2, padx=PAD_MD, pady=PAD_SM)
        install_focus_ring(self._open_folder_btn)
        Tooltip(self._open_folder_btn, "Abrir pasta de gravações")

    def set_source(self, device_label: str, model: str, backend: str) -> None:
        self._source_lbl.configure(text=f"Origem: {device_label}  •  Modelo: {model}  •  Backend: {backend}")

    def set_file(self, path: str | None) -> None:
        if path:
            import os
            self._file_lbl.configure(text=f"📁 {os.path.basename(path)}")
        else:
            self._file_lbl.configure(text="Nenhum arquivo")
