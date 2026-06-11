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
from src.nlp.answer_generator import LocalGenerator, APIGenerator
from src.nlp.summarizer import Summarizer
from src.config_store import config_store
from src.ui.region_selector import RegionSelector


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
        self._tab_summary_view = self._tabs.add("Resumo")
        self._tab_answers = self._tabs.add("Respostas")
        self._tab_config = self._tabs.add("Config")

        self._build_translation_tab()
        self._build_capture_tab()
        self._build_summary_tab()
        self._build_answers_tab()
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

        ctk.CTkLabel(frame, text="Modelo:").grid(
            row=0, column=0, padx=6, pady=6, sticky="w"
        )
        self._summary_model = ctk.CTkOptionMenu(
            frame, values=["gpt-3.5-turbo", "gpt-4"], width=160,
        )
        self._summary_model.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        ctk.CTkLabel(frame, text="Prompt Sistema:").grid(
            row=1, column=0, padx=6, pady=6, sticky="w"
        )
        self._sys_prompt = ctk.CTkEntry(
            frame, placeholder_text="Você é um assistente que resume reuniões.",
        )
        self._sys_prompt.grid(row=1, column=1, padx=6, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Prompt Usuário:").grid(
            row=2, column=0, padx=6, pady=6, sticky="w"
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

        self._use_api_ans = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            tab, text="Usar API DeepSeek/OpenAI",
            variable=self._use_api_ans,
        ).grid(row=2, column=0, padx=20, pady=4, sticky="w")

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
                model=self._summary_model.get(),
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
            if self._use_api_ans.get() if hasattr(self, '_use_api_ans') else False:
                gen = APIGenerator()
            else:
                gen = LocalGenerator()
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

    def _on_open_folder(self):
        path = settings.recording_dir
        if os.path.isdir(path):
            os.startfile(path)

    def _on_closing(self):
        self.session.stop()
        geometry = self._root.geometry()
        config_store.set("window_geometry", geometry)
        self._root.destroy()

    def run(self):
        self._root.mainloop()
