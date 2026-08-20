"""Painel lateral recolhível com abas: Tradução, Resumo, Resposta, Falantes."""
import customtkinter as ctk
from src.ui.theme import (
    Theme, BUTTON_HEIGHT, PAD_SM, PAD_MD,
    RESULTS_PANEL_WIDTH, install_focus_ring,
)
from src.ui.components.tooltip import Tooltip

# Cores de falantes (mantidas do app original)
_SPEAKER_COLORS = [
    "#3498db", "#e74c3c", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
]
_SPEAKER_COLOR_NAMES = [
    "Azul", "Vermelho", "Verde", "Laranja",
    "Roxo", "Turquesa", "Marrom", "Cinza",
]


class ResultsPanel(ctk.CTkFrame):
    def __init__(
        self, master,
        on_summarize, on_answer, on_set_context, on_translate,
        on_reprocess, on_speaker_map_changed,
        get_llm_config, on_save_llm, on_test_llm,
    ):
        super().__init__(master, corner_radius=0, fg_color=Theme.SURFACE, width=RESULTS_PANEL_WIDTH)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._visible = False

        self._on_summarize = on_summarize
        self._on_answer = on_answer
        self._on_set_context = on_set_context
        self._on_translate = on_translate
        self._on_reprocess = on_reprocess
        self._on_speaker_map_changed = on_speaker_map_changed
        self._get_llm_config = get_llm_config
        self._on_save_llm = on_save_llm
        self._on_test_llm = on_test_llm

        # Cabeçalho do painel: título + botão fechar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Resultados", font=Theme.heading(), text_color=Theme.TEXT).grid(row=0, column=0, sticky="w")
        self._close_btn = ctk.CTkButton(
            header, text="✕", width=32, height=32,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED,
            text_color=Theme.TEXT_MUTED, hover_color=Theme.BORDER,
            command=self.close,
        )
        self._close_btn.grid(row=0, column=1, sticky="e")
        install_focus_ring(self._close_btn)

        # Abas
        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=PAD_MD, pady=(0, PAD_MD))

        self._tab_translation = self._tabs.add("Tradução")
        self._tab_summary = self._tabs.add("Resumo")
        self._tab_answer = self._tabs.add("Resposta")
        self._tab_speakers = self._tabs.add("Falantes")

        self._build_translation_tab()
        self._build_summary_tab()
        self._build_answer_tab()
        self._build_speakers_tab()

    # --- Tradução -------------------------------------------------------------

    def _build_translation_tab(self):
        tab = self._tab_translation
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=PAD_MD, pady=(PAD_MD, 0))

        self._btn_translate = ctk.CTkButton(
            btn_row, text="Traduzir transcrição", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=self._on_translate,
        )
        self._btn_translate.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_translate)
        Tooltip(self._btn_translate, "Traduzir a transcrição completa para português")

        self._translation_box = ctk.CTkTextbox(
            tab, wrap="word", font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
        )
        self._translation_box.grid(row=1, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)

    def set_translation(self, text: str) -> None:
        self._translation_box.configure(state="normal")
        self._translation_box.delete("1.0", "end")
        self._translation_box.insert("1.0", text)
        self._translation_box.configure(state="disabled")

    def append_translation(self, text: str) -> None:
        self._translation_box.configure(state="normal")
        self._translation_box.insert("end", text + "\n")
        self._translation_box.see("end")
        self._translation_box.configure(state="disabled")

    # --- Resumo ---------------------------------------------------------------

    def _build_summary_tab(self):
        tab = self._tab_summary
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(6, weight=1)

        self._summary_provider_lbl = ctk.CTkLabel(
            tab, text="", font=Theme.label(), text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self._summary_provider_lbl.grid(row=0, column=0, padx=PAD_MD, pady=(PAD_MD, PAD_SM), sticky="w")

        frame = ctk.CTkFrame(tab)
        frame.grid(row=1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Prompt Sistema:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        self._sys_prompt = ctk.CTkEntry(frame, font=Theme.body(), placeholder_text="Você é um assistente que resume reuniões.")
        self._sys_prompt.grid(row=0, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._sys_prompt)

        ctk.CTkLabel(frame, text="Prompt Usuário:", font=Theme.label(), text_color=Theme.TEXT).grid(
            row=1, column=0, padx=PAD_MD, pady=PAD_MD, sticky="nw")
        self._user_prompt = ctk.CTkEntry(frame, font=Theme.body(), placeholder_text="Por favor, resuma o seguinte texto:")
        self._user_prompt.grid(row=1, column=1, padx=PAD_MD, pady=PAD_MD, sticky="ew")
        install_focus_ring(self._user_prompt)

        self._btn_summarize = ctk.CTkButton(
            tab, text="Gerar Resumo", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=lambda: self._on_summarize(
                self._sys_prompt.get() or None,
                self._user_prompt.get() or None,
            ),
        )
        self._btn_summarize.grid(row=2, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        install_focus_ring(self._btn_summarize)
        Tooltip(self._btn_summarize, "Gerar resumo do conteúdo capturado")

        self._summary_bar = ctk.CTkProgressBar(tab, mode="indeterminate")
        self._summary_bar.grid(row=3, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        self._summary_bar.grid_remove()

        self._summary_box = ctk.CTkTextbox(
            tab, wrap="word", font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
        )
        self._summary_box.grid(row=4, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)

    def show_summary_progress(self, show: bool) -> None:
        if show:
            self._summary_bar.grid()
            self._summary_bar.start()
        else:
            self._summary_bar.stop()
            self._summary_bar.grid_remove()

    def set_summary(self, text: str) -> None:
        self._summary_box.configure(state="normal")
        self._summary_box.delete("1.0", "end")
        self._summary_box.insert("1.0", text)
        self._summary_box.configure(state="disabled")

    def set_provider_label(self, text: str) -> None:
        self._summary_provider_lbl.configure(text=text)

    # --- Resposta -------------------------------------------------------------

    def _build_answer_tab(self):
        tab = self._tab_answer
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(6, weight=1)

        self._answer_provider_lbl = ctk.CTkLabel(
            tab, text="", font=Theme.label(), text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self._answer_provider_lbl.grid(row=0, column=0, padx=PAD_MD, pady=(PAD_MD, PAD_SM), sticky="w")

        # Contexto
        ctk.CTkLabel(tab, text="Contexto da reunião:", font=Theme.label_bold(), text_color=Theme.TEXT).grid(
            row=1, column=0, padx=PAD_MD, pady=(PAD_MD, PAD_SM), sticky="w")

        ctx_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ctx_frame.grid(row=2, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        ctx_frame.grid_columnconfigure(0, weight=1)

        self._ctx_box = ctk.CTkTextbox(ctx_frame, height=90, font=Theme.body(),
                                       fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
                                       border_width=1, border_color=Theme.BORDER)
        self._ctx_box.grid(row=0, column=0, sticky="ew", padx=(0, PAD_MD))
        install_focus_ring(self._ctx_box)

        ctx_btn_row = ctk.CTkFrame(ctx_frame, fg_color="transparent")
        ctx_btn_row.grid(row=0, column=1, sticky="ns")
        self._btn_set_ctx = ctk.CTkButton(
            ctx_btn_row, text="Definir Contexto", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=self._on_ctx_set,
        )
        self._btn_set_ctx.pack(side="left", padx=PAD_SM)
        install_focus_ring(self._btn_set_ctx)

        self._ctx_status = ctk.CTkLabel(ctx_btn_row, text="Contexto não definido", text_color=Theme.DANGER)
        self._ctx_status.pack(side="left", padx=PAD_MD)

        self._btn_answer = ctk.CTkButton(
            tab, text="Gerar Resposta", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=self._on_answer,
        )
        self._btn_answer.grid(row=3, column=0, padx=PAD_MD, pady=PAD_MD, sticky="w")
        install_focus_ring(self._btn_answer)
        Tooltip(self._btn_answer, "Gerar resposta para a última pergunta detectada")

        # Resultados lado a lado
        res_frame = ctk.CTkFrame(tab)
        res_frame.grid(row=4, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)
        res_frame.grid_columnconfigure(0, weight=1)
        res_frame.grid_columnconfigure(1, weight=1)
        res_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(res_frame, text="Globish", font=Theme.label_bold(), text_color=Theme.SUCCESS).grid(
            row=0, column=0, padx=PAD_MD, pady=(PAD_MD, PAD_SM), sticky="w")
        ctk.CTkLabel(res_frame, text="Tradução", font=Theme.label_bold(), text_color=Theme.PRIMARY).grid(
            row=0, column=1, padx=PAD_MD, pady=(PAD_MD, PAD_SM), sticky="w")

        self._ans_globish = ctk.CTkTextbox(
            res_frame, wrap="word", font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
        )
        self._ans_globish.grid(row=1, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)
        self._ans_pt = ctk.CTkTextbox(
            res_frame, wrap="word", font=Theme.body(),
            fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER,
        )
        self._ans_pt.grid(row=1, column=1, sticky="nsew", padx=PAD_MD, pady=PAD_MD)

    def _on_ctx_set(self):
        ctx = self._ctx_box.get("1.0", "end").strip()
        ok = self._on_set_context(ctx)
        if ok:
            self._ctx_status.configure(text="Contexto definido", text_color=Theme.SUCCESS)
        else:
            self._ctx_status.configure(text="Contexto vazio!", text_color=Theme.DANGER)

    def set_answer(self, globish: str, translated: str) -> None:
        self._ans_globish.configure(state="normal")
        self._ans_globish.delete("1.0", "end")
        self._ans_globish.insert("1.0", globish)
        self._ans_globish.configure(state="disabled")
        self._ans_pt.configure(state="normal")
        self._ans_pt.delete("1.0", "end")
        self._ans_pt.insert("1.0", translated)
        self._ans_pt.configure(state="disabled")

    def set_answer_provider_label(self, text: str) -> None:
        self._answer_provider_lbl.configure(text=text)

    # --- Falantes -------------------------------------------------------------

    def _build_speakers_tab(self):
        tab = self._tab_speakers
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Toolbar
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=PAD_MD, pady=(PAD_MD, 0))
        toolbar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(toolbar, text="Falantes:", font=Theme.label_bold(), text_color=Theme.TEXT).grid(
            row=0, column=0, padx=0, sticky="w")

        self._btn_add_speaker = ctk.CTkButton(
            toolbar, text="➕", width=36, height=36,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=lambda: self._add_speaker_row(),
        )
        self._btn_add_speaker.grid(row=0, column=1, padx=PAD_SM)
        install_focus_ring(self._btn_add_speaker)
        Tooltip(self._btn_add_speaker, "Adicionar falante")

        self._btn_clear_speakers = ctk.CTkButton(
            toolbar, text="✕ Limpar", width=90, height=36,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=self._clear_speaker_rows,
        )
        self._btn_clear_speakers.grid(row=0, column=3, padx=PAD_SM, sticky="e")
        install_focus_ring(self._btn_clear_speakers)
        Tooltip(self._btn_clear_speakers, "Limpar todos os falantes")

        # Scroll horizontal para linhas de falantes
        self._speaker_scroll = ctk.CTkScrollableFrame(tab, orientation="horizontal", height=80)
        self._speaker_scroll.grid(row=1, column=0, sticky="ew", padx=PAD_MD, pady=PAD_SM)
        self._speaker_rows: dict[str, dict] = {}

        # Ações
        action_row = ctk.CTkFrame(tab, fg_color="transparent")
        action_row.grid(row=2, column=0, sticky="ew", padx=PAD_MD, pady=PAD_MD)
        action_row.grid_columnconfigure(1, weight=1)

        self._btn_reprocess = ctk.CTkButton(
            action_row, text="Re-processar com Diarização", height=BUTTON_HEIGHT,
            font=Theme.button(), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
            command=self._on_reprocess,
            state="disabled",
        )
        self._btn_reprocess.grid(row=0, column=0, sticky="w")
        install_focus_ring(self._btn_reprocess)
        Tooltip(self._btn_reprocess, "Re-processar o áudio salvo com diarização offline")

    def _add_speaker_row(self, sid: str = "", name: str = "", color: str = ""):
        if not sid:
            sid = f"speaker_{len(self._speaker_rows)}"
        if sid in self._speaker_rows:
            return
        if not color:
            idx = min(len(self._speaker_rows), len(_SPEAKER_COLORS) - 1)
            color = _SPEAKER_COLORS[idx]

        row = ctk.CTkFrame(self._speaker_scroll, fg_color="transparent")
        row.pack(side="left", padx=4, pady=2, fill="x")

        ctk.CTkLabel(row, text=sid, font=Theme.mono()).pack(side="left", padx=2)

        name_var = ctk.StringVar(value=name)
        entry = ctk.CTkEntry(row, textvariable=name_var, width=110, font=Theme.body())
        entry.pack(side="left", padx=2)
        install_focus_ring(entry)

        color_var = ctk.StringVar(value=color)
        color_menu = ctk.CTkOptionMenu(
            row, values=_SPEAKER_COLORS, variable=color_var, width=80, font=Theme.label(),
        )
        color_menu.pack(side="left", padx=2)
        install_focus_ring(color_menu)

        del_btn = ctk.CTkButton(
            row, text="✕", width=28, height=28,
            font=Theme.button(), fg_color=Theme.SURFACE_ELEVATED, text_color=Theme.TEXT,
            border_width=1, border_color=Theme.BORDER, hover_color=Theme.BORDER,
            command=lambda s=sid: self._remove_speaker_row(s),
        )
        del_btn.pack(side="left", padx=2)
        install_focus_ring(del_btn)

        self._speaker_rows[sid] = {
            "name_var": name_var,
            "color_var": color_var,
            "frame": row,
        }
        self._on_speaker_map_changed()

    def _remove_speaker_row(self, sid: str):
        if sid in self._speaker_rows:
            self._speaker_rows[sid]["frame"].destroy()
            del self._speaker_rows[sid]
            self._on_speaker_map_changed()

    def _clear_speaker_rows(self):
        for sid in list(self._speaker_rows.keys()):
            self._speaker_rows[sid]["frame"].destroy()
        self._speaker_rows.clear()
        self._on_speaker_map_changed()

    def get_speaker_map(self) -> dict:
        mapping = {}
        for sid, widgets in self._speaker_rows.items():
            name = widgets["name_var"].get().strip()
            color = widgets["color_var"].get()
            if name:
                mapping[sid] = {"name": name, "color": color}
        return mapping

    def load_speaker_map(self, mapping: dict):
        self._clear_speaker_rows()
        for sid, info in mapping.items():
            self._add_speaker_row(sid, info.get("name", ""), info.get("color", ""))

    def get_speaker_display_name(self, sid: str | None) -> str:
        if not sid or sid not in self._speaker_rows:
            return ""
        name = self._speaker_rows[sid]["name_var"].get().strip()
        return f"● {name or sid}: "

    def set_reprocess_enabled(self, enabled: bool):
        self._btn_reprocess.configure(state="normal" if enabled else "disabled")

    # --- Painel recolhível ----------------------------------------------------

    def open(self, tab_name: str | None = None):
        if not self._visible:
            self._visible = True
            self.grid()
        if tab_name and tab_name in self._tabs._tab_dict:
            self._tabs.set(tab_name)

    def close(self):
        if self._visible:
            self._visible = False
            self.grid_remove()

    def toggle(self):
        if self._visible:
            self.close()
        else:
            self.open()

    @property
    def is_open(self) -> bool:
        return self._visible
