"""Toast/notificação temporária (ou fixa para perguntas)."""
import customtkinter as ctk
from src.ui.theme import Theme, PAD_SM, PAD_MD, PAD_LG


class Toast(ctk.CTkFrame):
    KIND_CONFIG = {
        "ok": ("TOAST_OK_BG", "TOAST_OK_TEXT"),
        "warn": ("TOAST_WARN_BG", "TOAST_WARN_TEXT"),
        "error": ("TOAST_ERROR_BG", "TOAST_ERROR_TEXT"),
        "question": ("TOAST_WARN_BG", "TOAST_WARN_TEXT"),
    }

    def __init__(self, master):
        super().__init__(master, corner_radius=8, fg_color="transparent")
        self._label = ctk.CTkLabel(
            self, text="", font=Theme.label_bold(), wraplength=500, justify="left",
            padx=PAD_MD, pady=PAD_SM,
        )
        self._label.pack(padx=PAD_MD, pady=PAD_MD)
        self._after_id = None
        self.grid_remove()

    def show(self, text: str, kind: str = "ok", sticky: bool = False, timeout_ms: int = 3500):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

        bg_attr, fg_attr = self.KIND_CONFIG.get(kind, self.KIND_CONFIG["ok"])
        bg = getattr(Theme, bg_attr)
        fg = getattr(Theme, fg_attr)
        mode = ctk.get_appearance_mode()
        idx = 0 if mode == "Light" else 1
        self.configure(fg_color=bg[idx])
        self._label.configure(text=text, text_color=fg[idx])

        self.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(0, PAD_MD))

        if not sticky:
            self._after_id = self.after(timeout_ms, self.hide)

    def hide(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.grid_remove()
