"""Barra de controles de gravação: seletor de dispositivo, botão principal, timer, erro, diarização."""
import customtkinter as ctk
from src.ui.theme import (
    Theme, BUTTON_HEIGHT, BUTTON_HEIGHT_PRIMARY,
    PAD_SM, PAD_MD, PAD_LG, install_focus_ring,
)
from src.ui.view_models.recording_state import RecordingState


class RecordingControls(ctk.CTkFrame):
    def __init__(
        self, master,
        on_toggle_recording,
        on_refresh_devices,
        on_diarize_changed,
    ):
        super().__init__(master, corner_radius=0, fg_color=Theme.SURFACE)
        self.grid_columnconfigure(1, weight=1)

        # Linha 0: Origem | menu | refresh | botão principal | timer
        ctk.CTkLabel(
            self, text="Origem:", font=Theme.label_bold(), text_color=Theme.TEXT,
        ).grid(row=0, column=0, padx=(PAD_LG, PAD_SM), pady=PAD_MD, sticky="w")

        self._device_var = ctk.StringVar()
        self._device_menu = ctk.CTkOptionMenu(
            self, values=["Carregando..."], width=300,
            variable=self._device_var, font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER, dropdown_fg_color=Theme.SURFACE,
            dropdown_text_color=Theme.TEXT,
        )
        self._device_menu.grid(row=0, column=1, padx=PAD_SM, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._device_menu)
        Tooltip(self._device_menu, "Selecionar dispositivo de áudio (🎤 microfone / 🔊 áudio do sistema)")

        self._refresh_btn = ctk.CTkButton(
            self, text="🔄", width=44, height=BUTTON_HEIGHT,
            font=Theme.button(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=on_refresh_devices,
        )
        self._refresh_btn.grid(row=0, column=2, padx=PAD_SM, pady=PAD_MD)
        install_focus_ring(self._refresh_btn)
        Tooltip(self._refresh_btn, "Atualizar lista de dispositivos")

        self._primary_btn = ctk.CTkButton(
            self, text="▶ Iniciar transcrição",
            height=BUTTON_HEIGHT_PRIMARY, font=Theme.button(),
            fg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER,
            command=on_toggle_recording,
        )
        self._primary_btn.grid(row=0, column=3, padx=PAD_MD, pady=PAD_MD)
        install_focus_ring(self._primary_btn)

        self._timer_lbl = ctk.CTkLabel(
            self, text="00:00:00", font=Theme.mono(), text_color=Theme.TEXT_MUTED,
        )
        self._timer_lbl.grid(row=0, column=4, padx=PAD_MD, pady=PAD_MD, sticky="e")

        # Linha 1: erro (esquerda) | diarização (direita)
        self._error_lbl = ctk.CTkLabel(
            self, text="", font=Theme.label(), text_color=Theme.DANGER,
            anchor="w",
        )
        self._error_lbl.grid(row=1, column=0, columnspan=4, padx=PAD_LG, pady=(0, PAD_MD), sticky="w")
        self._error_lbl.grid_remove()

        self._diarize_var = ctk.BooleanVar(value=True)
        self._diarize_cb = ctk.CTkCheckBox(
            self, text="🎤 Diarização em tempo real",
            variable=self._diarize_var, font=Theme.label(),
            command=on_diarize_changed,
        )
        self._diarize_cb.grid(row=1, column=4, padx=PAD_LG, pady=(0, PAD_MD), sticky="e")
        install_focus_ring(self._diarize_cb)
        Tooltip(self._diarize_cb, "Desligar se a CPU estiver muito alta; diarização ainda disponível no pós-processamento")

    # --- API pública ----------------------------------------------------------

    def set_devices(self, labels: list[str], selected: str | None = None) -> None:
        self._device_menu.configure(values=labels)
        if selected and selected in labels:
            self._device_var.set(selected)
        elif labels:
            self._device_var.set(labels[0])

    def selected_device(self) -> str:
        return self._device_var.get()

    def set_error(self, msg: str) -> None:
        self._error_lbl.configure(text=msg)
        self._error_lbl.grid()

    def clear_error(self) -> None:
        self._error_lbl.configure(text="")
        self._error_lbl.grid_remove()

    def apply_state(self, state: RecordingState) -> None:
        self._primary_btn.configure(
            text=state.primary_button_text,
            state="normal" if state.primary_button_enabled else "disabled",
            fg_color=Theme.DANGER if state.state == RecordingState.RECORDING else Theme.SUCCESS,
            hover_color=Theme.DANGER_HOVER if state.state == RecordingState.RECORDING else Theme.SUCCESS_HOVER,
        )

    def set_timer(self, text: str) -> None:
        self._timer_lbl.configure(text=text)

    def reset_timer(self) -> None:
        self._timer_lbl.configure(text="00:00:00")

    def diarize_enabled(self) -> bool:
        return self._diarize_var.get()

    def set_diarize_enabled(self, enabled: bool) -> None:
        self._diarize_var.set(enabled)


# Import tardio para evitar ciclo
from src.ui.components.tooltip import Tooltip  # noqa: E402
