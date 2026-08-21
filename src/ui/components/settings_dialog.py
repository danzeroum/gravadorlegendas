"""Diálogo modal de configurações: Aparência, IA, Captura de tela, Sistema."""
import customtkinter as ctk
from src.ui.theme import (
    Theme, BUTTON_HEIGHT, PAD_SM, PAD_MD, PAD_LG,
    SCALING_OPTIONS, scaling_label, install_focus_ring,
)
from src.ui.components.tooltip import Tooltip
from src.config_store import config_store


class SettingsDialog(ctk.CTkToplevel):
    def __init__(
        self, master,
        caps,
        on_theme_change, on_scaling_change, on_prefix_change,
        on_select_region,
        on_ocr_start, on_ocr_stop,
        llm_config_provider, on_save_llm, on_test_llm,
    ):
        super().__init__(master)
        self.title("Configurações")
        self.geometry("680x720")
        self.minsize(600, 560)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._caps = caps
        self._on_theme_change = on_theme_change
        self._on_scaling_change = on_scaling_change
        self._on_prefix_change = on_prefix_change
        self._select_region_callback = on_select_region
        self._on_ocr_start = on_ocr_start
        self._on_ocr_stop = on_ocr_stop
        self._llm_config_provider = llm_config_provider
        self._on_save_llm = on_save_llm
        self._on_test_llm = on_test_llm

        self._ia_field_widgets: dict[str, ctk.CTkEntry | ctk.CTkOptionMenu] = {}
        self._ia_provider_var = ctk.StringVar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Scrollable body
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)
        self._scroll.grid_columnconfigure(0, weight=1)

        self._build_appearance_section()
        self._build_ia_section()
        self._build_capture_section()
        self._build_system_section()

        # Botão fechar no rodapé
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_MD)
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            footer, text="Fechar", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED,
            text_color=Theme.TEXT, border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BORDER,
            command=self.close,
        ).grid(row=0, column=1, sticky="e")

        self.bind("<Escape>", lambda _e: self.close(), add="+")
        self.focus_set()

        # Carregar estado inicial
        self._load_initial()

    def _section_header(self, text: str, row: int):
        ctk.CTkLabel(
            self._scroll, text=text,
            font=Theme.heading(), text_color=Theme.PRIMARY[0],
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(PAD_LG, PAD_SM))

    def _build_appearance_section(self):
        row = 0
        self._section_header("Aparência", row)

        # Tema
        frame = ctk.CTkFrame(self._scroll)
        frame.grid(row=row + 1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text="Tema:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        self._theme_seg = ctk.CTkSegmentedButton(
            frame, values=["Claro", "Escuro"],
            font=Theme.button(), height=BUTTON_HEIGHT,
            command=lambda v: self._on_theme_change("dark" if v == "Escuro" else "light"),
        )
        self._theme_seg.grid(row=0, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._theme_seg)

        # Escala
        frame2 = ctk.CTkFrame(self._scroll)
        frame2.grid(row=row + 2, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame2.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame2, text="Escala da interface:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        self._scale_var = ctk.StringVar()
        self._scale_menu = ctk.CTkOptionMenu(
            frame2, values=list(SCALING_OPTIONS.keys()),
            variable=self._scale_var, font=Theme.body(),
            command=lambda v: self._on_scaling_change(SCALING_OPTIONS[v]),
        )
        self._scale_menu.grid(row=0, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._scale_menu)
        Tooltip(self._scale_menu, "Requer reinício do aplicativo para aplicar")

        self._scale_note = ctk.CTkLabel(
            frame2, text="",
            font=Theme.label(), text_color=Theme.WARNING[0],
            anchor="w",
        )
        self._scale_note.grid(row=1, column=0, columnspan=2, padx=PAD_MD, pady=(0, PAD_MD), sticky="w")

        # Prefixo do arquivo
        frame3 = ctk.CTkFrame(self._scroll)
        frame3.grid(row=row + 3, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame3.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame3, text="Prefixo do arquivo:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        self._prefix_var = ctk.StringVar()
        self._prefix_entry = ctk.CTkEntry(frame3, textvariable=self._prefix_var, font=Theme.body(),
                                          placeholder_text="legendas")
        self._prefix_entry.grid(row=0, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._prefix_entry)
        self._prefix_entry.bind("<KeyRelease>", lambda _e: self._on_prefix_change(self._prefix_var.get()))

    def _build_ia_section(self):
        row = 4
        self._section_header("IA", row)

        # Provider
        frame = ctk.CTkFrame(self._scroll)
        frame.grid(row=row + 1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text="Provedor ativo:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        self._provider_menu = ctk.CTkOptionMenu(
            frame, values=["openai", "deepseek", "ollama", "local_gguf"],
            variable=self._ia_provider_var, font=Theme.body(),
            command=self._on_provider_changed,
        )
        self._provider_menu.grid(row=0, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._provider_menu)
        Tooltip(self._provider_menu, "Selecionar o provedor de IA ativo")

        # Campos dinâmicos
        self._ia_fields_frame = ctk.CTkFrame(self._scroll)
        self._ia_fields_frame.grid(row=row + 2, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        self._ia_fields_frame.grid_columnconfigure(1, weight=1)

        # Botões
        btn_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        btn_row.grid(row=row + 3, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)

        self._btn_test_llm = ctk.CTkButton(
            btn_row, text="Testar Conexão", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=self._on_test_llm_clicked,
        )
        self._btn_test_llm.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_test_llm)
        Tooltip(self._btn_test_llm, "Envia um prompt de teste para o provedor ativo")

        self._btn_save_llm = ctk.CTkButton(
            btn_row, text="Salvar Configuração", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER,
            command=self._on_save_llm_clicked,
        )
        self._btn_save_llm.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_save_llm)
        Tooltip(self._btn_save_llm, "Persiste as configurações do provedor ativo")

        self._ia_status = ctk.CTkLabel(btn_row, text="", font=Theme.label(), text_color=Theme.TEXT_MUTED)
        self._ia_status.pack(side="left", padx=PAD_MD)

    def _on_provider_changed(self, choice: str):
        self._rebuild_ia_fields()
        self._populate_ia_fields(choice)

    def _rebuild_ia_fields(self):
        for w in self._ia_field_widgets.values():
            w.destroy()
        self._ia_field_widgets.clear()

        provider = self._ia_provider_var.get()
        schema = {
            "openai": [("api_key", "API Key", True), ("model", "Modelo", False)],
            "deepseek": [("api_key", "API Key", True), ("model", "Modelo", False)],
            "ollama": [
                ("base_url", "URL Base", False),
                ("model", "Modelo", False),
                ("username", "Usuário", False),
                ("__password_env__", "Senha", False),
            ],
            "local_gguf": [
                ("model_path", "Caminho .gguf", False),
                ("n_ctx", "Contexto (tokens)", False),
                ("n_threads", "Threads", False),
            ],
        }
        fields = schema.get(provider, [])
        for i, (key, label, is_secret) in enumerate(fields):
            lbl = ctk.CTkLabel(self._ia_fields_frame, text=f"{label}:", font=Theme.label(), text_color=Theme.TEXT)
            lbl.grid(row=i, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
            if key == "__password_env__":
                entry = ctk.CTkLabel(
                    self._ia_fields_frame, text="🔒 Gerenciado via .env",
                    font=Theme.label(), text_color=Theme.TEXT_MUTED,
                )
                entry.grid(row=i, column=1, padx=PAD_MD, pady=PAD_MD, sticky="w")
            elif key == "model" and provider == "ollama":
                models = ["mistral:latest", "llama3", "llama3.1", "codellama", "phi3", "deepseek-coder"]
                entry = ctk.CTkOptionMenu(self._ia_fields_frame, values=models, font=Theme.body())
                entry.grid(row=i, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
            else:
                show_char = "*" if is_secret else ""
                entry = ctk.CTkEntry(self._ia_fields_frame, font=Theme.body(), show=show_char)
                entry.grid(row=i, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
                install_focus_ring(entry)
            self._ia_field_widgets[key] = entry

    def _populate_ia_fields(self, provider: str):
        cfg = self._llm_config_provider(provider)
        for key, widget in self._ia_field_widgets.items():
            value = cfg.get(key, "")
            if isinstance(widget, ctk.CTkEntry):
                widget.delete(0, "end")
                widget.insert(0, str(value))
            elif isinstance(widget, ctk.CTkOptionMenu):
                widget.set(str(value) if value else widget._values[0])

    def _collect_ia_fields(self) -> dict:
        data = {}
        for key, widget in self._ia_field_widgets.items():
            if isinstance(widget, ctk.CTkEntry):
                data[key] = widget.get()
            elif isinstance(widget, ctk.CTkOptionMenu):
                data[key] = widget.get()
        return data

    def _on_save_llm_clicked(self):
        provider = self._ia_provider_var.get()
        fields = self._collect_ia_fields()
        self._on_save_llm(provider, fields)
        self._ia_status.configure(text="Configuração salva", text_color=Theme.SUCCESS)

    def _on_test_llm_clicked(self):
        self._ia_status.configure(text="Testando…", text_color=Theme.WARNING[0])
        self._on_test_llm(lambda ok, msg: self._after_test(ok, msg))

    def _after_test(self, ok: bool, msg: str):
        self._ia_status.configure(
            text="Conexão OK!" if ok else f"Falha: {msg[:80]}",
            text_color=Theme.SUCCESS if ok else Theme.DANGER,
        )

    # --- Captura de tela (OCR) ---

    def _build_capture_section(self):
        row = 7
        self._section_header("Captura de tela (OCR)", row)

        # Banner de plataforma
        caps_text = self._platform_banner_text()
        self._platform_lbl = ctk.CTkLabel(
            self._scroll, text=caps_text,
            font=Theme.label(), text_color=self._platform_banner_color(),
            anchor="w", justify="left",
        )
        self._platform_lbl.grid(row=row + 1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)

        # Região
        region = config_store.get("screen_region", {"top": 0, "left": 50, "width": 1820, "height": 80})
        frame = ctk.CTkFrame(self._scroll)
        frame.grid(row=row + 2, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame.grid_columnconfigure(1, weight=1)

        self._region_lbl = ctk.CTkLabel(
            frame, text=f"Região: top={region['top']}, left={region['left']}, width={region['width']}, height={region['height']}",
            font=Theme.label(), text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self._region_lbl.grid(row=0, column=0, columnspan=2, padx=PAD_MD, pady=PAD_MD, sticky="w")

        self._btn_region = ctk.CTkButton(
            frame, text="Selecionar Região", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=self._handle_select_region,
        )
        self._btn_region.grid(row=1, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        install_focus_ring(self._btn_region)
        Tooltip(self._btn_region, "Abrir overlay para arrastar e definir a área de captura")

        # Checkbox legendas do Windows (só Windows)
        if self._caps.supports_windows_live_captions:
            self._activate_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                frame, text="Ativar legendas do Windows (Win+Ctrl+L)",
                variable=self._activate_var, font=Theme.label(),
            ).grid(row=2, column=0, columnspan=2, padx=PAD_MD, pady=PAD_SM, sticky="w")

        # Botões Iniciar/Parar OCR
        ocr_btn_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        ocr_btn_row.grid(row=row + 3, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)

        self._btn_ocr_start = ctk.CTkButton(
            ocr_btn_row, text="Iniciar Captura OCR", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER,
            command=self._on_ocr_start_clicked,
        )
        self._btn_ocr_start.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_ocr_start)
        Tooltip(self._btn_ocr_start, "Iniciar captura de tela + OCR (não funciona em Wayland sem portal)")

        self._btn_ocr_stop = ctk.CTkButton(
            ocr_btn_row, text="Parar Captura OCR", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER,
            command=self._on_ocr_stop_clicked,
            state="disabled",
        )
        self._btn_ocr_stop.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_ocr_stop)

        self._ocr_status = ctk.CTkLabel(ocr_btn_row, text="", font=Theme.label(), text_color=Theme.TEXT_MUTED)
        self._ocr_status.pack(side="left", padx=PAD_MD)

    def _platform_banner_text(self) -> str:
        c = self._caps
        parts = [f"💻 {c.os.value.upper()}"]
        if c.is_linux:
            parts.append(f"sessão {c.session.value.upper()}")
            if c.pipewire_available:
                parts.append("PipeWire ✓")
            elif c.pulseaudio_available:
                parts.append("PulseAudio ✓")
            else:
                parts.append("sem servidor de áudio ✗")
            if c.is_wayland:
                if c.supports_portal_screen_capture:
                    parts.append("portal detectado")
                else:
                    parts.append("Wayland sem portal ✗")
        return "  ·  ".join(parts)

    def _platform_banner_color(self) -> str:
        if self._caps.is_wayland and not self._caps.supports_screen_capture:
            return Theme.DANGER[0]
        if not self._caps.pipewire_available and not self._caps.pulseaudio_available:
            return Theme.DANGER[0]
        return Theme.SUCCESS[0]

    def _handle_select_region(self):
        region = self._select_region_callback()
        if region:
            self._region_lbl.configure(
                text=f"Região: top={region['top']}, left={region['left']}, width={region['width']}, height={region['height']}"
            )

    def _on_ocr_start_clicked(self):
        prefix = self._prefix_var.get().strip() or "legendas"
        activate = self._activate_var.get() if hasattr(self, "_activate_var") else True
        msg = self._on_ocr_start(prefix, activate)
        if "Erro" in msg:
            self._ocr_status.configure(text=msg, text_color=Theme.DANGER)
        else:
            self._ocr_status.configure(text=msg, text_color=Theme.SUCCESS)
            self._btn_ocr_start.configure(state="disabled")
            self._btn_ocr_stop.configure(state="normal")

    def _on_ocr_stop_clicked(self):
        msg = self._on_ocr_stop()
        self._ocr_status.configure(text=msg, text_color=Theme.TEXT_MUTED)
        self._btn_ocr_start.configure(state="normal")
        self._btn_ocr_stop.configure(state="disabled")

    # --- Sistema ---

    def _build_system_section(self):
        row = 11
        self._section_header("Sistema", row)

        fields = [
            ("Sistema operacional", self._caps.os.value),
            ("Sessão gráfica", self._caps.session.value),
            ("Backend de áudio", self._caps.audio_backend if hasattr(self._caps, 'audio_backend') else "auto"),
            ("Backend de captura", "mss" if not self._caps.is_wayland else "portal"),
            ("STT model", "base"),
            ("STT device", "auto"),
        ]
        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(self._scroll, text=f"{label}:", font=Theme.label(), text_color=Theme.TEXT_MUTED).grid(
                row=row + 1 + i, column=0, padx=PAD_MD, pady=PAD_SM, sticky="w")
            ctk.CTkLabel(
                self._scroll, text=str(value),
                font=Theme.mono(), text_color=Theme.TEXT_MUTED,
            ).grid(row=row + 1 + i, column=1, padx=PAD_MD, pady=PAD_SM, sticky="w")

        ctk.CTkLabel(
            self._scroll,
            text=("As configurações multiplataforma são lidas do arquivo .env\n"
                  "(PLATFORM_BACKEND, AUDIO_BACKEND, AUDIO_SOURCE, CAPTION_SOURCE,\n"
                  "SCREEN_CAPTURE_BACKEND, STT_MODEL, STT_DEVICE, SAMPLE_RATE, CHANNELS)."),
            font=Theme.label(), text_color=Theme.TEXT_MUTED, justify="left",
        ).grid(row=row + len(fields) + 2, column=0, padx=PAD_MD, pady=PAD_LG, sticky="w")

    def _load_initial(self):
        # Tema
        theme = config_store.get("theme", "light")
        self._theme_seg.set("Escuro" if theme == "dark" else "Claro")

        # Escala
        scaling = config_store.get("ui_scaling", 1.0)
        self._scale_var.set(scaling_label(scaling))
        self._update_scale_note(scaling)

        # Prefixo
        self._prefix_var.set(config_store.get("last_prefix", "legendas"))

        # IA
        llm_cfg = self._llm_config_provider("")  # chama provider vazio p/ pegar active
        active = llm_cfg.get("active_provider", "ollama")
        self._ia_provider_var.set(active)
        self._rebuild_ia_fields()
        self._populate_ia_fields(active)

    def _update_scale_note(self, factor: float):
        if abs(factor - 1.0) > 0.001:
            self._scale_note.configure(text="⚠ A escala será aplicada ao reiniciar o aplicativo")
        else:
            self._scale_note.configure(text="")

    # --- API pública para app.py ---

    def close(self):
        self.grab_release()
        self.destroy()
