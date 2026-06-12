"""Interface gráfica principal com CustomTkinter.

Layout:
- Barra superior: título + toggle tema
- Barra de botões globais: Iniciar, Parar, Resumo, Responder + LED status
- CTkTabview: Tradução (3 colunas), Captura, Resumo, Respostas, Config
- Banner de notificação para perguntas detectadas
- Rodapé: arquivo atual + abrir pasta
"""
import os
import threading
import customtkinter as ctk

from src.config import settings
from src.main import SessionManager
from src.translation.api import TranslatorAPI
from src.nlp.answer_generator import ManagedGenerator
from src.nlp.summarizer import Summarizer
from src.config_store import config_store
from src.ui.region_selector import RegionSelector
from src.llm.manager import llm_manager
from src.audio.manager import AudioManager


class Tooltip:
    """Tooltip simples para CTkButton via eventos Enter/Leave."""

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip_window = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)

    def _enter(self, event=None):
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 5
        self._tip_window = ctk.CTkToplevel(self._widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(
            self._tip_window, text=self._text,
            fg_color="#333333", text_color="white",
            corner_radius=4, padx=8, pady=4,
            font=ctk.CTkFont(size=11),
        )
        label.pack()

    def _leave(self, event=None):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


class MainWindow:
    """Janela principal com CustomTkinter."""

    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.session = SessionManager()
        self._translator_api = TranslatorAPI()
        self._summarizer = Summarizer()
        self._audio_manager = AudioManager()

        self._root = ctk.CTk()
        self._root.title("Gravador de Legendas")
        geometry = config_store.get("window_geometry", "960x680")
        self._root.geometry(geometry)
        self._root.minsize(800, 600)

        theme = config_store.get("theme", "light")
        self._is_dark = theme == "dark"
        ctk.set_appearance_mode(theme)

        self._build_ui()
        self._bind_shortcuts()

        saved_prefix = config_store.get("last_prefix", "legendas")
        if hasattr(self, '_prefix_var'):
            self._prefix_var.set(saved_prefix)

        if not llm_manager._initialized:
            llm_manager.initialize()

        self._update_provider_labels()

        self.session.on_captured = self._on_captured
        self.session.on_translated = self._on_translated
        self.session.on_question = self._on_question

        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        self._root.grid_columnconfigure(0, weight=1)
        self._root.grid_rowconfigure(2, weight=1)

        self._build_top_bar()
        self._build_button_bar()
        self._build_tab_view()
        self._build_notification_banner()
        self._build_footer()

    # ---- Top bar ----
    def _build_top_bar(self):
        frame = ctk.CTkFrame(self._root, corner_radius=0)
        frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="Gravador de Legendas",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=15, pady=8, sticky="w")

        self._theme_btn = ctk.CTkButton(
            frame, text="☀️ Claro", width=90,
            command=self._toggle_theme,
        )
        self._theme_btn.grid(row=0, column=1, padx=10, pady=8, sticky="e")

    # ---- Button bar ----
    def _build_button_bar(self):
        frame = ctk.CTkFrame(self._root, corner_radius=0)
        frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        frame.grid_columnconfigure(4, weight=1)

        self._btn_start = ctk.CTkButton(
            frame, text="▶️ Iniciar", command=self._on_start,
            fg_color="#2c8c5a", hover_color="#1f6e48",
            width=120,
        )
        self._btn_start.grid(row=0, column=0, padx=6, pady=8)
        Tooltip(self._btn_start, "Iniciar captura (Ctrl+I)")

        self._btn_stop = ctk.CTkButton(
            frame, text="⏹️ Parar", command=self._on_stop,
            fg_color="#c0392b", hover_color="#962d22",
            width=120, state="disabled",
        )
        self._btn_stop.grid(row=0, column=1, padx=6, pady=8)
        Tooltip(self._btn_stop, "Parar captura (Ctrl+P)")

        self._btn_summary = ctk.CTkButton(
            frame, text="📄 Resumo", command=self._on_summarize,
            width=120,
        )
        self._btn_summary.grid(row=0, column=2, padx=6, pady=8)
        Tooltip(self._btn_summary, "Gerar resumo do texto capturado (Ctrl+S)")

        self._btn_answer = ctk.CTkButton(
            frame, text="💬 Responder", command=self._on_answer,
            width=120,
        )
        self._btn_answer.grid(row=0, column=3, padx=6, pady=8)
        Tooltip(self._btn_answer, "Gerar resposta para a última pergunta (Ctrl+R)")

        self._status_led = ctk.CTkLabel(
            frame, text="● Parado",
            font=ctk.CTkFont(size=13), text_color="gray",
        )
        self._status_led.grid(row=0, column=4, padx=15, pady=8, sticky="e")

    # ---- Tab view ----
    def _build_tab_view(self):
        self._tabs = ctk.CTkTabview(self._root)
        self._tabs.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        self._tab_translation = self._tabs.add("Tradução")
        self._tab_capture = self._tabs.add("Captura")
        self._tab_audio = self._tabs.add("Áudio")
        self._tab_summary_view = self._tabs.add("Resumo")
        self._tab_answers = self._tabs.add("Respostas")
        self._tab_ia = self._tabs.add("IA")
        self._tab_config = self._tabs.add("Config")

        self._build_translation_tab()
        self._build_capture_tab()
        self._build_audio_tab()
        self._build_summary_tab()
        self._build_answers_tab()
        self._build_ia_tab()
        self._build_config_tab()

    # ---- Notification banner ----
    def _build_notification_banner(self):
        self._notif_frame = ctk.CTkFrame(
            self._root, corner_radius=0, fg_color="#fff3cd"
        )
        self._notif_frame.grid(row=3, column=0, sticky="ew", padx=0, pady=0)
        self._notif_frame.grid_columnconfigure(0, weight=1)

        self._notif_label = ctk.CTkLabel(
            self._notif_frame, text="",
            font=ctk.CTkFont(size=12), text_color="#856404",
        )
        self._notif_label.grid(row=0, column=0, padx=15, pady=6, sticky="w")

        self._notif_frame.grid_remove()

    # ---- Footer ----
    def _build_footer(self):
        frame = ctk.CTkFrame(self._root, corner_radius=0, fg_color="transparent")
        frame.grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        frame.grid_columnconfigure(0, weight=1)

        self._file_label = ctk.CTkLabel(
            frame, text="Nenhum arquivo",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._file_label.grid(row=0, column=0, padx=5, sticky="w")

        self._btn_open_folder = ctk.CTkButton(
            frame, text="📂 Abrir Pasta", width=100,
            command=self._on_open_folder,
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
        )
        self._btn_open_folder.grid(row=0, column=1, padx=5)

    # ========= Aba Tradução (3 colunas) =========
    def _build_translation_tab(self):
        tab = self._tab_translation
        tab.grid_columnconfigure(0, weight=1, uniform="col")
        tab.grid_columnconfigure(1, weight=1, uniform="col")
        tab.grid_columnconfigure(2, weight=1, uniform="col")
        tab.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            tab, text="Original (EN)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=6, pady=(8, 2), sticky="w")

        ctk.CTkLabel(
            tab, text="Tradução (PT)",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#1a6fb5",
        ).grid(row=0, column=1, padx=6, pady=(8, 2), sticky="w")

        ctk.CTkLabel(
            tab, text="Resposta", font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2c8c5a",
        ).grid(row=0, column=2, padx=6, pady=(8, 2), sticky="w")

        self._orig_text = ctk.CTkTextbox(
            tab, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._orig_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        self._trans_text = ctk.CTkTextbox(
            tab, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._trans_text.grid(row=1, column=1, sticky="nsew", padx=6, pady=4)

        ans_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ans_frame.grid(row=1, column=2, sticky="nsew", padx=6, pady=4)
        ans_frame.grid_rowconfigure(1, weight=1)
        ans_frame.grid_columnconfigure(0, weight=1)

        self._btn_generate = ctk.CTkButton(
            ans_frame, text="💬 Gerar Resposta",
            command=self._on_answer, height=32,
        )
        self._btn_generate.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._ans_text = ctk.CTkTextbox(
            ans_frame, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._ans_text.grid(row=1, column=0, sticky="nsew")

    # ========= Aba Captura =========
    def _build_capture_tab(self):
        tab = self._tab_capture
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tab, text="Configurações de Captura",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(15, 5))

        frame = ctk.CTkFrame(tab)
        frame.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(frame, text="Prefixo do arquivo:").pack(pady=(10, 2))
        self._prefix_var = ctk.StringVar(value="legendas")
        ctk.CTkEntry(frame, textvariable=self._prefix_var, width=300).pack(pady=4)

        self._activate_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            frame, text="Ativar legendas do Windows (Win+Ctrl+L)",
            variable=self._activate_var,
        ).pack(pady=6)

        self._region_label = ctk.CTkLabel(
            frame,
            text=f"Região: top={settings.screen_region['top']}, "
            f"left={settings.screen_region['left']}, "
            f"width={settings.screen_region['width']}, "
            f"height={settings.screen_region['height']}",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._region_label.pack(pady=(8, 4))

        self._btn_region = ctk.CTkButton(
            frame, text="🎯 Selecionar Região",
            command=self._on_select_region, width=200,
        )
        self._btn_region.pack(pady=6)
        Tooltip(self._btn_region, "Abrir overlay para arrastar e definir a área de captura")

    # ========= Aba Áudio =========
    def _build_audio_tab(self):
        tab = self._tab_audio
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            tab, text="Captura de Áudio (WASAPI)",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(15, 8))

        frame = ctk.CTkFrame(tab)
        frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=4)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Dispositivo:").grid(
            row=0, column=0, padx=6, pady=6, sticky="w"
        )
        self._audio_device_var = ctk.StringVar()
        self._audio_device_menu = ctk.CTkOptionMenu(
            frame, values=["Carregando..."], width=350,
            variable=self._audio_device_var,
        )
        self._audio_device_menu.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        Tooltip(self._audio_device_menu, "Selecionar dispositivo WASAPI para captura")

        ctk.CTkButton(
            frame, text="🔄 Atualizar Dispositivos",
            command=self._refresh_audio_devices, width=180,
        ).grid(row=0, column=2, padx=6, pady=6)
        Tooltip(self._audio_device_menu, "Atualizar lista de dispositivos WASAPI")

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=2, pady=10)

        self._btn_audio_start = ctk.CTkButton(
            btn_row, text="🎤 Iniciar Captura", command=self._on_audio_start,
            fg_color="#2c8c5a", hover_color="#1f6e48", width=160,
        )
        self._btn_audio_start.pack(side="left", padx=6)
        Tooltip(self._btn_audio_start, "Iniciar captura de áudio e transcrição")

        self._btn_audio_stop = ctk.CTkButton(
            btn_row, text="⏹️ Parar Captura", command=self._on_audio_stop,
            fg_color="#c0392b", hover_color="#962d22",
            width=160, state="disabled",
        )
        self._btn_audio_stop.pack(side="left", padx=6)
        Tooltip(self._btn_audio_stop, "Parar captura de áudio")

        self._audio_status = ctk.CTkLabel(
            tab, text="", font=ctk.CTkFont(size=12), text_color="gray",
        )
        self._audio_status.grid(row=3, column=0, columnspan=2, padx=20, pady=4, sticky="w")

        ctk.CTkLabel(
            tab, text="Transcrição ao Vivo:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=4, column=0, padx=20, pady=(8, 2), sticky="sw")

        self._audio_transcript = ctk.CTkTextbox(
            tab, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._audio_transcript.grid(
            row=4, column=0, columnspan=2, sticky="nsew", padx=20, pady=(28, 8)
        )

        self._audio_translated = ctk.CTkTextbox(
            tab, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._audio_translated.grid(
            row=4, column=1, columnspan=2, sticky="nsew", padx=20, pady=(28, 8)
        )

        ctk.CTkLabel(
            tab, text="Tradução:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=4, column=1, padx=20, pady=(8, 2), sticky="sw")

        self._audio_manager.on_transcription = self._on_audio_transcription
        self._audio_manager.on_error = self._on_audio_error

        self._refresh_audio_devices()

    def _refresh_audio_devices(self):
        devices = self._audio_manager.list_devices()
        if not devices:
            self._audio_device_menu.configure(
                values=["Nenhum dispositivo WASAPI encontrado"]
            )
            self._audio_device_var.set("Nenhum dispositivo WASAPI encontrado")
            return
        names = [f"{d['index']}: {d['name']}" for d in devices]
        self._audio_device_menu.configure(values=names)
        self._audio_device_var.set(names[0])

    # ========= Aba Resumo =========
    def _build_summary_tab(self):
        tab = self._tab_summary_view
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            tab, text="Resumo da Reunião",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, pady=(15, 8))

        frame = ctk.CTkFrame(tab)
        frame.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        frame.grid_columnconfigure(1, weight=1)

        self._summary_provider_label = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._summary_provider_label.grid(row=0, column=0, columnspan=2, padx=6, pady=2, sticky="w")

        ctk.CTkLabel(frame, text="Prompt Sistema:").grid(
            row=1, column=0, padx=6, pady=6, sticky="w"
        )
        self._sys_prompt = ctk.CTkEntry(
            frame, placeholder_text="Você é um assistente que resume reuniões.",
        )
        self._sys_prompt.grid(row=1, column=1, padx=6, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Prompt Usuário:").grid(
            row=2, column=0, padx=6, pady=6, sticky="nw"
        )
        self._user_prompt = ctk.CTkEntry(
            frame, placeholder_text="Por favor, resuma o seguinte texto:",
        )
        self._user_prompt.grid(row=2, column=1, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(
            tab, text="📄 Gerar Resumo", command=self._on_summarize,
            width=160,
        ).grid(row=2, column=0, pady=10)

        self._summary_bar = ctk.CTkProgressBar(tab, mode="indeterminate")
        self._summary_bar.grid(row=3, column=0, sticky="ew", padx=40, pady=4)
        self._summary_bar.grid_remove()

        self._summary_result = ctk.CTkTextbox(
            tab, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._summary_result.grid(row=5, column=0, sticky="nsew", padx=20, pady=8)

    # ========= Aba Respostas =========
    def _build_answers_tab(self):
        tab = self._tab_answers
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            tab, text="Sugestão de Respostas (Globish)",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, pady=(15, 8))

        frame = ctk.CTkFrame(tab)
        frame.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Contexto da reunião:").grid(
            row=0, column=0, padx=6, pady=6, sticky="nw"
        )
        self._ctx_text = ctk.CTkTextbox(frame, height=70, font=ctk.CTkFont(size=12))
        self._ctx_text.grid(row=0, column=1, padx=6, pady=6, sticky="ew")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=1, column=1, padx=6, pady=4, sticky="w")
        ctk.CTkButton(
            btn_row, text="Definir Contexto",
            command=self._on_set_context, width=140,
        ).pack(side="left", padx=4)
        self._ctx_status = ctk.CTkLabel(
            btn_row, text="Contexto não definido", text_color="red"
        )
        self._ctx_status.pack(side="left", padx=8)

        self._ans_provider_label = ctk.CTkLabel(
            tab, text="",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._ans_provider_label.grid(row=2, column=0, padx=20, pady=2, sticky="w")

        ctk.CTkButton(
            tab, text="💬 Responder (Gerar Globish)",
            command=self._on_answer, width=220,
        ).grid(row=3, column=0, pady=10)

        res_frame = ctk.CTkFrame(tab)
        res_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=8)
        res_frame.grid_columnconfigure(0, weight=1)
        res_frame.grid_columnconfigure(1, weight=1)
        res_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            res_frame, text="Globish", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#2c8c5a",
        ).grid(row=0, column=0, padx=4, sticky="w")
        ctk.CTkLabel(
            res_frame, text="Tradução", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1a6fb5",
        ).grid(row=0, column=1, padx=4, sticky="w")

        self._ans_globish = ctk.CTkTextbox(
            res_frame, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._ans_globish.grid(row=1, column=0, sticky="nsew", padx=4)
        self._ans_pt = ctk.CTkTextbox(
            res_frame, wrap="word", font=ctk.CTkFont(size=12),
        )
        self._ans_pt.grid(row=1, column=1, sticky="nsew", padx=4)

    # ========= Aba IA =========
    def _build_ia_tab(self):
        tab = self._tab_ia
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            tab, text="Configuração de IA",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(15, 8))

        # Provedor ativo
        ctk.CTkLabel(tab, text="Provedor ativo:").grid(
            row=1, column=0, padx=10, pady=6, sticky="w"
        )
        self._ia_provider_var = ctk.StringVar(value="openai")
        self._ia_provider_menu = ctk.CTkOptionMenu(
            tab, values=["openai", "deepseek", "ollama", "local_gguf"],
            variable=self._ia_provider_var,
            command=self._on_provider_changed,
            width=200,
        )
        self._ia_provider_menu.grid(row=1, column=1, padx=10, pady=6, sticky="w")
        Tooltip(self._ia_provider_menu, "Selecionar o provedor de IA ativo")

        # Campos dinâmicos do provider
        self._ia_fields_frame = ctk.CTkFrame(tab)
        self._ia_fields_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        self._ia_fields_frame.grid_columnconfigure(1, weight=1)

        self._ia_field_widgets: dict[str, ctk.CTkEntry | ctk.CTkOptionMenu] = {}

        # Botões
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=2, pady=10)

        self._btn_test_llm = ctk.CTkButton(
            btn_row, text="🔌 Testar Conexão",
            command=self._on_test_llm, width=160,
        )
        self._btn_test_llm.pack(side="left", padx=6)
        Tooltip(self._btn_test_llm, "Envia um prompt de teste para o provedor ativo")

        self._btn_save_llm = ctk.CTkButton(
            btn_row, text="💾 Salvar Configuração",
            command=self._on_save_llm_config, width=180,
        )
        self._btn_save_llm.pack(side="left", padx=6)
        Tooltip(self._btn_save_llm, "Persiste as configurações do provedor ativo")

        self._ia_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self._ia_status.grid(row=4, column=0, columnspan=2, padx=10, pady=4)

        # Carregar valores salvos
        self._load_ia_config()

    def _load_ia_config(self):
        llm_cfg = config_store.get_llm_config()
        active = llm_cfg.get("active_provider", "openai")
        self._ia_provider_var.set(active)
        self._rebuild_ia_fields()
        self._populate_ia_fields(active)

    def _rebuild_ia_fields(self):
        for w in self._ia_field_widgets.values():
            w.destroy()
        self._ia_field_widgets.clear()

        provider = self._ia_provider_var.get()
        schema = {
            "openai":     [("api_key", "API Key", True), ("model", "Modelo", False)],
            "deepseek":   [("api_key", "API Key", True), ("model", "Modelo", False)],
            "ollama":     [
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
        for i, (key, label, _) in enumerate(fields):
            lbl = ctk.CTkLabel(self._ia_fields_frame, text=f"{label}:")
            lbl.grid(row=i, column=0, padx=6, pady=4, sticky="w")
            if key == "__password_env__":
                entry = ctk.CTkLabel(
                    self._ia_fields_frame, text="🔒 Gerenciado via .env",
                    font=ctk.CTkFont(size=11), text_color="gray",
                )
                entry.grid(row=i, column=1, padx=6, pady=4, sticky="w")
            elif key == "model" and provider == "ollama":
                models = [
                    "mistral:latest", "llama3", "llama3.1",
                    "codellama", "phi3", "deepseek-coder",
                ]
                entry = ctk.CTkOptionMenu(
                    self._ia_fields_frame, values=models, width=200,
                )
                entry.grid(row=i, column=1, padx=6, pady=4, sticky="ew")
            else:
                show_char = "*" if "key" in key else ""
                entry = ctk.CTkEntry(self._ia_fields_frame, width=300, show=show_char)
                entry.grid(row=i, column=1, padx=6, pady=4, sticky="ew")
            self._ia_field_widgets[key] = entry

    def _populate_ia_fields(self, provider: str):
        prov_cfg = config_store.get_llm_provider_config(provider)
        for key, widget in self._ia_field_widgets.items():
            value = prov_cfg.get(key, "")
            if isinstance(widget, ctk.CTkEntry):
                widget.delete(0, "end")
                widget.insert(0, str(value))
            elif isinstance(widget, ctk.CTkOptionMenu):
                widget.set(str(value) if value else widget._values[0])

    def _on_provider_changed(self, choice: str):
        self._rebuild_ia_fields()
        self._populate_ia_fields(choice)

    def _collect_ia_fields(self) -> dict:
        data = {}
        for key, widget in self._ia_field_widgets.items():
            if isinstance(widget, ctk.CTkEntry):
                data[key] = widget.get()
            elif isinstance(widget, ctk.CTkOptionMenu):
                data[key] = widget.get()
        return data

    def _on_save_llm_config(self):
        provider = self._ia_provider_var.get()
        prov_cfg = self._collect_ia_fields()
        config_store.set_llm_provider_config(provider, prov_cfg)
        llm_cfg = config_store.get_llm_config()
        llm_cfg["active_provider"] = provider
        config_store.set_llm_config(llm_cfg)
        if not llm_manager._initialized:
            llm_manager.initialize()
        llm_manager.switch_provider(provider, prov_cfg)
        self._update_provider_labels()
        self._ia_status.configure(text="Configuração salva com sucesso.", text_color="green")

    def _on_test_llm(self):
        self._on_save_llm_config()
        self._ia_status.configure(text="Testando conexão...", text_color="gray")

        def task():
            result = llm_manager.generate("Say 'connection ok' and nothing else.", max_tokens=10)
            success = "Erro" not in result and "connection ok" in result.lower()[:20]
            color = "green" if success else "red"
            label = "Conexão OK!" if success else f"Falha: {result[:80]}"
            self._root.after(0, lambda: self._ia_status.configure(text=label, text_color=color))

        threading.Thread(target=task, daemon=True).start()

    # ========= Aba Config =========
    def _build_config_tab(self):
        tab = self._tab_config
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            tab, text="Configurações",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(15, 8))

        fields = [
            ("Região Top", str(settings.screen_region["top"])),
            ("Região Left", str(settings.screen_region["left"])),
            ("Região Width", str(settings.screen_region["width"])),
            ("Região Height", str(settings.screen_region["height"])),
            ("Idioma OCR", settings.ocr_language),
            ("Modelo Tradução", settings.translation_model),
            ("Diretório Gravação", settings.recording_dir),
            ("Wordlist", settings.wordlist_path),
        ]

        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(tab, text=label + ":").grid(
                row=i + 1, column=0, padx=10, pady=4, sticky="w"
            )
            ctk.CTkLabel(
                tab, text=value, font=ctk.CTkFont(size=11, family="Consolas"),
                text_color="gray",
            ).grid(row=i + 1, column=1, padx=10, pady=4, sticky="w")

        ctk.CTkLabel(
            tab, text="As configurações são lidas do arquivo .env",
            font=ctk.CTkFont(size=11), text_color="gray",
        ).grid(row=len(fields) + 2, column=0, columnspan=2, pady=20)

    # ---- Theme toggle ----
    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        mode = "dark" if self._is_dark else "light"
        ctk.set_appearance_mode(mode)
        self._theme_btn.configure(text="🌙 Escuro" if not self._is_dark else "☀️ Claro")
        config_store.set("theme", mode)

    # ---- Keyboard shortcuts ----
    def _bind_shortcuts(self):
        self._root.bind("<Control-i>", lambda e: self._on_start())
        self._root.bind("<Control-p>", lambda e: self._on_stop())
        self._root.bind("<Control-r>", lambda e: self._on_answer())
        self._root.bind("<Control-s>", lambda e: self._on_summarize())
        self._root.bind("<Control-e>", lambda e: self._on_set_context())

    # ---- Callbacks SessionManager ----
    def _on_captured(self, text: str):
        self._root.after(0, lambda: self._append_text(self._orig_text, text))

    def _on_translated(self, original: str, translated: str):
        self._root.after(0, lambda: self._append_text(self._trans_text, translated))

    def _on_question(self, text: str):
        self._root.after(0, self._show_notification, text)

    @staticmethod
    def _append_text(widget: ctk.CTkTextbox, text: str):
        widget.insert("1.0", text + "\n")
        widget.see("1.0")

    def _show_notification(self, text: str):
        self._notif_label.configure(
            text="🔔 Pergunta detectada! "
            "Clique em \"Responder\" para sugerir uma resposta."
        )
        self._notif_frame.grid()

    def _hide_notification(self):
        self._notif_frame.grid_remove()

    # ---- Botões ---->
    def _set_recording_state(self, running: bool):
        state = "normal" if not running else "disabled"
        disabled_state = "disabled" if not running else "normal"
        self._btn_start.configure(state=state)
        self._btn_stop.configure(state=disabled_state)
        if running:
            self._status_led.configure(text="● Ativo", text_color="#2c8c5a")
        else:
            self._status_led.configure(text="● Parado", text_color="gray")

    def _on_audio_start(self):
        devices = self._audio_manager.list_devices()
        if not devices:
            self._audio_status.configure(
                text="Nenhum dispositivo WASAPI encontrado.", text_color="red"
            )
            return
        idx = int(self._audio_device_var.get().split(":")[0])
        self._audio_status.configure(text="Iniciando captura...", text_color="gray")
        self._audio_manager.start(device_index=idx)
        self._btn_audio_start.configure(state="disabled")
        self._btn_audio_stop.configure(state="normal")
        self._audio_status.configure(
            text="🎤 Capturando áudio e transcrevendo...", text_color="#2c8c5a"
        )

    def _on_audio_stop(self):
        self._audio_manager.stop()
        self._btn_audio_start.configure(state="normal")
        self._btn_audio_stop.configure(state="disabled")
        self._audio_status.configure(text="⏹️ Captura parada.", text_color="gray")

    def _on_audio_transcription(self, text: str):
        self._root.after(0, lambda: self._append_text(self._audio_transcript, text))

    def _on_audio_error(self, error: str):
        self._root.after(
            0,
            lambda: self._audio_status.configure(
                text=f"Erro: {error}", text_color="red"
            ),
        )

    def _on_start(self):
        prefix = self._prefix_var.get().strip() if hasattr(
            self, '_prefix_var'
        ) else "legendas"
        activate = self._activate_var.get() if hasattr(
            self, '_activate_var'
        ) else True
        msg = self.session.start(prefix, activate)
        if "Erro" in msg:
            self._status_led.configure(text=msg, text_color="red")
        else:
            self._set_recording_state(True)
            self._file_label.configure(text=f"📁 {self.session.current_file}")
            config_store.set("last_prefix", prefix)

    def _on_stop(self):
        msg = self.session.stop()
        self._set_recording_state(False)
        self._status_led.configure(text=msg, text_color="gray")

    def _on_summarize(self):
        full_text = self.session.get_full_text()
        if not full_text:
            self._summary_result.insert("1.0", "Nenhum texto capturado.")
            return

        def task():
            self._root.after(0, self._summary_bar.grid)
            self._root.after(0, self._summary_bar.start)
            result = self._summarizer.summarize(
                text=full_text,
                system_prompt=self._sys_prompt.get() or None,
                user_prompt=self._user_prompt.get() or None,
            )
            self._root.after(0, lambda: self._show_summary(result))

        threading.Thread(target=task, daemon=True).start()
        self._summary_result.delete("1.0", "end")
        self._summary_result.insert("1.0", "Gerando resumo...")

    def _show_summary(self, summary: str):
        self._summary_bar.stop()
        self._summary_bar.grid_remove()
        self._summary_result.delete("1.0", "end")
        self._summary_result.insert("1.0", summary)

    def _on_set_context(self):
        if not hasattr(self, '_ctx_text'):
            return
        ctx = self._ctx_text.get("1.0", "end").strip()
        self.session.context = ctx
        if ctx:
            self._ctx_status.configure(text="Contexto definido.", text_color="green")
        else:
            self._ctx_status.configure(text="Contexto vazio!", text_color="red")

    def _on_answer(self):
        question = self.session.last_question
        if not question:
            self._status_led.configure(
                text="Nenhuma pergunta detectada.", text_color="red"
            )
            return
        if not self.session.context:
            self._status_led.configure(
                text="Defina o contexto primeiro.", text_color="red"
            )
            return

        def task():
            gen = ManagedGenerator()
            answer = gen.generate(question, self.session.context)
            translated = self.session.translator.translate(answer)
            self._root.after(0, lambda: self._show_answer(answer, translated))

        threading.Thread(target=task, daemon=True).start()
        self._ans_text.delete("1.0", "end")
        self._ans_text.insert("1.0", "Gerando resposta...")

    def _show_answer(self, answer: str, translated: str):
        self._ans_text.delete("1.0", "end")
        self._ans_text.insert("1.0", answer)
        if hasattr(self, '_ans_globish'):
            self._ans_globish.delete("1.0", "end")
            self._ans_globish.insert("1.0", answer)
        if hasattr(self, '_ans_pt'):
            self._ans_pt.delete("1.0", "end")
            self._ans_pt.insert("1.0", translated)
        self._hide_notification()
        self._status_led.configure(text="Resposta gerada.", text_color="#2c8c5a")

    def _on_select_region(self):
        selector = RegionSelector()
        region = selector.select()
        settings.screen_region = region
        config_store.set_region(region)
        if hasattr(self, '_region_label'):
            self._region_label.configure(
                text=f"Região: top={region['top']}, "
                f"left={region['left']}, "
                f"width={region['width']}, "
                f"height={region['height']}"
            )

    def _provider_display(self) -> str:
        """Retorna string legível do provedor ativo para exibir na UI."""
        name = llm_manager.active_provider or "nenhum"
        info = llm_manager.list_providers()
        for p in info:
            if p["name"] == name:
                model = p.get("model", "")
                if model:
                    return f"🤖 {name} · {model}"
                return f"🤖 {name}"
        return f"🤖 {name}"

    def _update_provider_labels(self):
        text = self._provider_display()
        if hasattr(self, '_summary_provider_label'):
            self._summary_provider_label.configure(text=text)
        if hasattr(self, '_ans_provider_label'):
            self._ans_provider_label.configure(text=text)

    def _on_open_folder(self):
        path = settings.recording_dir
        if os.path.isdir(path):
            os.startfile(path)

    def _on_closing(self):
        self.session.stop()
        if self._audio_manager.is_running:
            self._audio_manager.stop()
        geometry = self._root.geometry()
        config_store.set("window_geometry", geometry)
        self._root.destroy()

    def run(self):
        self._root.mainloop()
