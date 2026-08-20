"""Tooltip simples para CTk widgets via eventos Enter/Leave."""
import customtkinter as ctk


class Tooltip:
    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip_window = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")

    def _enter(self, event=None):
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 5
        self._tip_window = ctk.CTkToplevel(self._widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")
        from src.ui.theme import Theme
        label = ctk.CTkLabel(
            self._tip_window, text=self._text,
            fg_color=Theme.SURFACE_ELEVATED[0] if ctk.get_appearance_mode() == "Light" else Theme.SURFACE_ELEVATED[1],
            text_color=Theme.TEXT[0] if ctk.get_appearance_mode() == "Light" else Theme.TEXT[1],
            corner_radius=4, padx=8, pady=4,
            font=Theme.label(),
        )
        label.pack()

    def _leave(self, event=None):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None
