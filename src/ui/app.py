import threading
from tkinter import (
    Tk, Label, Button, Entry, Text, Checkbutton, BooleanVar,
    StringVar, OptionMenu, END, messagebox, ttk, DISABLED, NORMAL,
)

from src.config import settings
from src.main import SessionManager
from src.translation.api import TranslatorAPI
from src.nlp.answer_generator import LocalGenerator, APIGenerator
from src.nlp.summarizer import Summarizer


class MainWindow:
    def __init__(self):
        self.session = SessionManager()
        self._translator_api = TranslatorAPI()
        self._summarizer = Summarizer()

        self._root = Tk()
        self._root.title("Assistente de Reunião")
        self._root.geometry("840x650")
        self._root.resizable(False, False)

        self._build_ui()

        self.session.on_captured = self._on_captured
        self.session.on_translated = self._on_translated
        self.session.on_question = self._on_question

        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        notebook = ttk.Notebook(self._root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self._tab_capture = ttk.Frame(notebook)
        self._tab_translation = ttk.Frame(notebook)
        self._tab_summary = ttk.Frame(notebook)
        self._tab_answers = ttk.Frame(notebook)

        notebook.add(self._tab_capture, text="Captura")
        notebook.add(self._tab_translation, text="Tradução")
        notebook.add(self._tab_summary, text="Resumo")
        notebook.add(self._tab_answers, text="Respostas")

        self._build_capture_tab()
        self._build_translation_tab()
        self._build_summary_tab()
        self._build_answers_tab()

    # ---- Aba Captura ----
    def _build_capture_tab(self):
        frame = self._tab_capture
        Label(
            frame, text="Gravador de Legendas ao Vivo", font=("Arial", 16),
        ).pack(pady=10)

        Label(frame, text="Prefixo do arquivo:", font=("Arial", 12)).pack(pady=5)
        self._prefix_var = StringVar(value="legendas")
        Entry(frame, textvariable=self._prefix_var, font=("Arial", 12)).pack(pady=5)

        self._activate_captions_var = BooleanVar(value=True)
        Checkbutton(
            frame,
            text="Ativar legendas do Windows (Win+Ctrl+L)",
            variable=self._activate_captions_var,
        ).pack(pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)
        self._btn_start = Button(
            btn_frame, text="Iniciar Gravação", font=("Arial", 12),
            bg="green", fg="white", command=self._on_start,
        )
        self._btn_start.pack(side="left", padx=5)
        self._btn_stop = Button(
            btn_frame, text="Parar Gravação", font=("Arial", 12),
            bg="red", fg="white", command=self._on_stop, state=DISABLED,
        )
        self._btn_stop.pack(side="left", padx=5)

        self._status_label = Label(frame, text="Pronto", font=("Arial", 12), fg="blue")
        self._status_label.pack(pady=10)

        Label(
            frame, text="Região de captura: "
            f"top={settings.screen_region['top']}, "
            f"left={settings.screen_region['left']}, "
            f"width={settings.screen_region['width']}, "
            f"height={settings.screen_region['height']}",
            font=("Arial", 9), fg="gray",
        ).pack(side="bottom", pady=5)

    # ---- Aba Tradução ----
    def _build_translation_tab(self):
        frame = self._tab_translation
        Label(frame, text="Tradução em Tempo Real", font=("Arial", 16)).pack(pady=10)

        Label(
            frame, text="Texto original:",
            font=("Arial", 12, "bold"), anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 2))
        self._original_text = Text(frame, height=5, font=("Arial", 11), wrap="word")
        self._original_text.pack(fill="x", padx=10, pady=2)

        Label(
            frame, text="Tradução:",
            font=("Arial", 12, "bold"), anchor="w", fg="blue",
        ).pack(fill="x", padx=10, pady=(10, 2))
        self._translated_text = Text(
            frame, height=5, font=("Arial", 11), wrap="word", fg="blue"
        )
        self._translated_text.pack(fill="x", padx=10, pady=2)

        self._use_api_translate = BooleanVar(value=False)
        Checkbutton(
            frame,
            text="Usar API para tradução (requer chave configurada)",
            variable=self._use_api_translate,
        ).pack(pady=5)

        Label(
            frame,
            text="Modelo de tradução local: " + settings.translation_model,
            font=("Arial", 9), fg="gray",
        ).pack(side="bottom", pady=5)

    # ---- Aba Resumo ----
    def _build_summary_tab(self):
        frame = self._tab_summary
        Label(frame, text="Resumo da Reunião", font=("Arial", 16)).pack(pady=10)

        Label(frame, text="Modelo:", font=("Arial", 12)).pack(pady=5)
        self._summary_model_var = StringVar(value="gpt-3.5-turbo")
        OptionMenu(
            frame, self._summary_model_var, "gpt-3.5-turbo", "gpt-4"
        ).pack(pady=5)

        Label(frame, text="Prompt do Sistema:", font=("Arial", 12)).pack(pady=5)
        self._system_prompt_var = StringVar(
            value="Você é um assistente que resume reuniões."
        )
        Entry(
            frame, textvariable=self._system_prompt_var,
            font=("Arial", 12), width=60,
        ).pack(pady=5)

        Label(frame, text="Prompt do Usuário:", font=("Arial", 12)).pack(pady=5)
        self._user_prompt_var = StringVar(
            value="Por favor, resuma o seguinte texto:"
        )
        Entry(
            frame, textvariable=self._user_prompt_var,
            font=("Arial", 12), width=60,
        ).pack(pady=5)

        Button(
            frame, text="Gerar Resumo", font=("Arial", 12),
            bg="blue", fg="white", command=self._on_summarize,
        ).pack(pady=10)

        self._summary_result = Text(frame, height=12, font=("Arial", 11), wrap="word")
        self._summary_result.pack(fill="both", expand=True, padx=10, pady=5)

    # ---- Aba Respostas ----
    def _build_answers_tab(self):
        frame = self._tab_answers
        Label(
            frame, text="Sugestão de Respostas (Globish)",
            font=("Arial", 16),
        ).pack(pady=10)

        Label(
            frame, text="Contexto da reunião:",
            font=("Arial", 12, "bold"),
        ).pack(pady=5)
        self._context_text = Text(frame, height=4, font=("Arial", 11))
        self._context_text.pack(fill="x", padx=10, pady=2)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        Button(
            btn_frame, text="Definir Contexto",
            command=self._on_set_context, bg="lightgray",
        ).pack(side="left", padx=5)
        self._context_status = Label(btn_frame, text="Contexto não definido", fg="red")
        self._context_status.pack(side="left", padx=5)

        self._use_api_answer = BooleanVar(value=False)
        Checkbutton(
            frame,
            text="Usar API DeepSeek/OpenAI (requer chave configurada)",
            variable=self._use_api_answer,
        ).pack(pady=5)

        self._question_indicator = Label(
            frame, text="", font=("Arial", 11, "bold"), fg="orange",
        )
        self._question_indicator.pack(fill="x", padx=10, pady=5)

        Button(
            frame, text="Responder (Gerar Globish)", font=("Arial", 12, "bold"),
            bg="lightblue", command=self._on_answer, height=2,
        ).pack(pady=10)

        Label(
            frame, text="Resposta (Globish):",
            font=("Arial", 11, "bold"), fg="green",
        ).pack(anchor="w", padx=10)
        self._answer_globish = Text(
            frame, height=3, font=("Arial", 11), wrap="word", fg="green"
        )
        self._answer_globish.pack(fill="x", padx=10, pady=2)

        Label(frame, text="Tradução:", font=("Arial", 11, "bold"), fg="purple").pack(
            anchor="w", padx=10
        )
        self._answer_pt = Text(
            frame, height=3, font=("Arial", 11), wrap="word", fg="purple"
        )
        self._answer_pt.pack(fill="x", padx=10, pady=2)

    # ---- Callbacks SessionManager ----
    def _on_captured(self, text: str):
        self._root.after(0, self._append_original, text)

    def _on_translated(self, original: str, translated: str):
        self._root.after(0, self._update_translation, original, translated)

    def _on_question(self, text: str):
        self._root.after(0, self._show_question_notification, text)

    def _append_original(self, text: str):
        self._original_text.insert("1.0", text + "\n")
        self._original_text.see("1.0")

    def _update_translation(self, original: str, translated: str):
        self._translated_text.insert("1.0", f"{translated}\n")
        self._translated_text.see("1.0")

    def _show_question_notification(self, text: str):
        self._question_indicator.config(
            text="Possível pergunta detectada! Clique em 'Responder'.", fg="orange"
        )

    # ---- Botões Captura ----
    def _on_start(self):
        prefix = self._prefix_var.get().strip()
        msg = self.session.start(prefix, self._activate_captions_var.get())
        if "Erro" in msg:
            self._status_label.config(text=msg, fg="red")
        else:
            self._status_label.config(text=msg, fg="green")
            self._btn_start.config(state=DISABLED)
            self._btn_stop.config(state=NORMAL)

    def _on_stop(self):
        msg = self.session.stop()
        self._status_label.config(text=msg, fg="blue")
        self._btn_start.config(state=NORMAL)
        self._btn_stop.config(state=DISABLED)

    # ---- Botão Resumo ----
    def _on_summarize(self):
        full_text = self.session.get_full_text()
        if not full_text:
            messagebox.showwarning(
                "Aviso", "Nenhum texto capturado. Grave uma reunião primeiro."
            )
            return

        def task():
            result = self._summarizer.summarize(
                text=full_text,
                model=self._summary_model_var.get(),
                system_prompt=self._system_prompt_var.get(),
                user_prompt=self._user_prompt_var.get(),
            )
            self._root.after(0, lambda: self._show_summary(result))

        threading.Thread(target=task, daemon=True).start()
        self._summary_result.delete("1.0", END)
        self._summary_result.insert("1.0", "Gerando resumo...")

    def _show_summary(self, summary: str):
        self._summary_result.delete("1.0", END)
        self._summary_result.insert("1.0", summary)

    # ---- Botão Respostas ----
    def _on_set_context(self):
        ctx = self._context_text.get("1.0", END).strip()
        self.session.context = ctx
        if ctx:
            self._context_status.config(text="Contexto definido.", fg="green")
        else:
            self._context_status.config(text="Contexto vazio!", fg="red")

    def _on_answer(self):
        question = self.session.last_question
        if not question:
            self._question_indicator.config(
                text="Nenhuma pergunta detectada ainda.", fg="red"
            )
            return
        if not self.session.context:
            messagebox.showwarning(
                "Aviso", "Defina o contexto da reunião antes de responder."
            )
            return

        def task():
            if self._use_api_answer.get():
                gen = APIGenerator()
            else:
                gen = LocalGenerator()
            answer = gen.generate(question, self.session.context)
            translated = self.session.translator.translate(answer)
            self._root.after(0, lambda: self._show_answer(answer, translated))

        threading.Thread(target=task, daemon=True).start()
        self._answer_globish.delete("1.0", END)
        self._answer_globish.insert("1.0", "Gerando resposta...")

    def _show_answer(self, answer: str, translated: str):
        self._answer_globish.delete("1.0", END)
        self._answer_globish.insert("1.0", answer)
        self._answer_pt.delete("1.0", END)
        self._answer_pt.insert("1.0", translated)
        self._question_indicator.config(text="Resposta gerada.", fg="green")

    def _on_closing(self):
        self.session.stop()
        self._root.destroy()

    def run(self):
        self._root.mainloop()
