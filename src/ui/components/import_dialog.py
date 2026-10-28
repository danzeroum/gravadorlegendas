"""Diálogo de importação de áudio/vídeo (Frente J do plano de diarização)."""
import os

import customtkinter as ctk

from src.config import settings
from src.ui.theme import Theme, BUTTON_HEIGHT, PAD_SM, PAD_MD, PAD_LG, install_focus_ring
from src.ui.components.tooltip import Tooltip
from src.ui.view_models.import_job import WHISPER_CHOICES, parse_participants


class ImportDialog(ctk.CTkToplevel):
    """Opções antes de transcrever um arquivo importado.

    ``on_confirm(options)`` recebe ``{"model_size", "num_speakers", "diarize"}``.
    """

    def __init__(self, master, path: str, on_confirm):
        super().__init__(master)
        self.title("Importar áudio")
        self.geometry("560x380")
        self.minsize(480, 340)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._on_confirm = on_confirm
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text=f"📄 {os.path.basename(path)}",
            font=Theme.heading(), text_color=Theme.TEXT, anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD_MD))

        self._diarize_var = ctk.BooleanVar(value=True)
        diarize_cb = ctk.CTkCheckBox(
            self, text="Separar participantes pela voz (A, B, C…)",
            variable=self._diarize_var, font=Theme.label(),
            command=self._sync_participants_state,
        )
        diarize_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD_SM)
        install_focus_ring(diarize_cb)

        ctk.CTkLabel(
            self, text="Nº de participantes:", font=Theme.label(), text_color=Theme.TEXT,
        ).grid(row=2, column=0, sticky="w", padx=(PAD_LG, PAD_SM), pady=PAD_SM)
        self._participants = ctk.CTkEntry(
            self, placeholder_text="opcional — melhora a separação", font=Theme.body(),
        )
        self._participants.grid(row=2, column=1, sticky="ew", padx=(0, PAD_LG), pady=PAD_SM)
        install_focus_ring(self._participants)
        Tooltip(self._participants, "Se souber quantas pessoas falam no áudio, informe aqui")

        ctk.CTkLabel(
            self, text="Modelo:", font=Theme.label(), text_color=Theme.TEXT,
        ).grid(row=3, column=0, sticky="w", padx=(PAD_LG, PAD_SM), pady=PAD_SM)
        choices = list(WHISPER_CHOICES)
        if settings.stt_model not in choices:
            choices.insert(0, settings.stt_model)
        self._model_var = ctk.StringVar(value=settings.stt_model)
        model_menu = ctk.CTkOptionMenu(
            self, values=choices, variable=self._model_var, font=Theme.body(),
        )
        model_menu.grid(row=3, column=1, sticky="w", padx=(0, PAD_LG), pady=PAD_SM)
        install_focus_ring(model_menu)
        Tooltip(model_menu, "Para conversa natural gravada no celular, 'small' costuma acertar mais (mais lento)")

        self._error = ctk.CTkLabel(self, text="", font=Theme.label(), text_color=Theme.DANGER, anchor="w")
        self._error.grid(row=4, column=0, columnspan=2, sticky="ew", padx=PAD_LG)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, columnspan=2, sticky="ew", padx=PAD_LG, pady=PAD_LG)
        footer.grid_columnconfigure(0, weight=1)
        cancel_btn = ctk.CTkButton(
            footer, text="Cancelar", height=BUTTON_HEIGHT, font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=self.destroy,
        )
        cancel_btn.grid(row=0, column=1, padx=PAD_SM)
        install_focus_ring(cancel_btn)
        ok_btn = ctk.CTkButton(
            footer, text="▶ Transcrever", height=BUTTON_HEIGHT, font=Theme.button(),
            fg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER,
            command=self._confirm,
        )
        ok_btn.grid(row=0, column=2)
        install_focus_ring(ok_btn)

        self.bind("<Return>", lambda _e: self._confirm(), add="+")
        self.bind("<Escape>", lambda _e: self.destroy(), add="+")
        self._participants.focus_set()

    def _sync_participants_state(self):
        self._participants.configure(state="normal" if self._diarize_var.get() else "disabled")

    def _confirm(self):
        diarize = self._diarize_var.get()
        try:
            num = parse_participants(self._participants.get()) if diarize else None
        except ValueError as e:
            self._error.configure(text=str(e))
            return
        options = {"model_size": self._model_var.get(), "num_speakers": num, "diarize": diarize}
        self.destroy()
        self._on_confirm(options)
