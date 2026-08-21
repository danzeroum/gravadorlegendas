"""Interface gráfica principal com CustomTkinter — reformulada.

Layout:
- Header: título + status pill + tema + configurações
- RecordingControls: seletor PipeWire + ▶/■ principal + timer + diarização
- TranscriptionPanel: área central flexível com Copiar/Salvar/Exportar/Limpar
- ResultsPanel (lateral, recolhível): Tradução / Resumo / Resposta / Falantes
- Toast: notificações temporárias
- StatusBar: origem/dispositivo/modelo + arquivo + abrir pasta
- SettingsDialog (modal): Aparência / IA / Captura OCR / Sistema

Fluxo prioritário:
    Origem PipeWire → Iniciar/Parar → Transcrição ao vivo → Salvar/Copiar/Exportar
Tradução, Resumo, Resposta e IA ficam no painel lateral sob demanda.
"""
import os
import shutil
import subprocess
import sys
import time
import threading
import tkinter.messagebox as tkmsg
import customtkinter as ctk

from src.config import settings, validate_settings
from src.main import SessionManager
from src.translation.api import TranslatorAPI
from src.nlp.answer_generator import ManagedGenerator
from src.nlp.summarizer import Summarizer
from src.config_store import config_store
from src.ui.region_selector import RegionSelector
from src.llm.manager import llm_manager
from src.audio.manager import AudioManager
from src.platform.detection import detect_capabilities, PlatformCapabilities

from src.ui.theme import (
    apply_widget_scaling, resolve_widget_scaling,
)
from src.ui.shortcuts import SHORTCUTS
from src.ui.view_models.recording_state import RecordingState, RecordingStateMachine, format_duration
from src.ui.components import (
    Header, RecordingControls, TranscriptionPanel,
    ResultsPanel, StatusBar, Toast, SettingsDialog,
)


def _open_folder_crossplatform(path: str) -> None:
    if not os.path.isdir(path):
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", path])


def apply_speaker_map(panel, mapping: dict) -> None:
    """Carrega um mapping de falantes persistido em um ResultsPanel.

    Helper puro e headless-friendly usado no startup da janela principal.
    """
    if mapping and hasattr(panel, "load_speaker_map"):
        panel.load_speaker_map(mapping)


class MainWindow:
    """Janela principal do Gravador de Legendas."""

    def __init__(self):
        # Capacidades de plataforma
        self._caps: PlatformCapabilities = detect_capabilities()

        # Serviços
        self.session = SessionManager()
        self._translator_api = TranslatorAPI()
        self._summarizer = Summarizer()
        self._audio_manager = AudioManager()

        # Estado de apresentação
        self._machine = RecordingStateMachine()
        self._audio_transcript_lines: list[str] = []

        # Metadados de dispositivos (label -> meta)
        self._audio_devices_meta: list[dict] = []

        # UI - ESCALA ANTES de criar CTk()
        # Em Linux/HiDPI as constantes de tema (fontes, dimensoes) sao
        # multiplicadas pela escala detectada em src/ui/theme.py; a janela
        # tambem e escalada la. No Windows usamos o widget_scaling normal.
        if sys.platform.startswith("linux"):
            apply_widget_scaling(1.0)
        else:
            ui_scaling = config_store.get("ui_scaling", 1.0)
            apply_widget_scaling(resolve_widget_scaling(stored=ui_scaling))

        ctk.set_appearance_mode(config_store.get("theme", "light"))
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("Gravador de Legendas")
        geometry = config_store.get("window_geometry", "1100x720")
        self._root.geometry(geometry)
        self._root.minsize(960, 600)

        self._is_dark = config_store.get("theme", "light") == "dark"
        self._closing = False

        # Construção da UI
        self._build_ui()
        self._bind_shortcuts()

        # Carregar speaker map persistido
        self._load_speaker_map()

        # Restaurar prefixo (persistido no SettingsDialog)
        _ = config_store.get("last_prefix", "legendas")

        # Inicializar LLM manager
        if not llm_manager._initialized:
            llm_manager.initialize()

        self._update_provider_labels()

        # Callbacks do SessionManager (fluxo OCR)
        self.session.on_captured = self._on_captured
        self.session.on_translated = self._on_translated
        self.session.on_question = self._on_question

        # Callbacks do AudioManager
        self._audio_manager.on_transcription = self._on_audio_transcription
        self._audio_manager.on_error = self._on_audio_error

        # Avisos iniciais
        errors = validate_settings()
        if errors:
            self._root.after(
                500,
                lambda: self._toast.show(
                    "⚠ Configuração inválida: " + "; ".join(errors[:2]),
                    kind="warn",
                ),
            )

        if self._caps.is_wayland and not self._caps.supports_screen_capture:
            self._root.after(
                800,
                lambda: self._toast.show(
                    "⚠ Wayland detectado sem portal de captura. Use sessão Xorg para OCR de tela.",
                    kind="warn",
                    timeout_ms=8000,
                ),
            )

        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Carregar dispositivos de áudio
        self._refresh_audio_devices()

    # -------------------------------------------------------------------------
    # Construção da UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        self._root.grid_columnconfigure(0, weight=1)
        self._root.grid_rowconfigure(2, weight=1)  # linha do conteúdo

        # Linha 0: Header
        self._header = Header(
            self._root,
            on_toggle_theme=self._toggle_theme,
            on_open_settings=self._open_settings,
        )
        self._header.grid(row=0, column=0, sticky="ew")

        # Linha 1: Controles de gravação
        self._controls = RecordingControls(
            self._root,
            on_toggle_recording=self._on_toggle_recording,
            on_refresh_devices=self._refresh_audio_devices,
            on_diarize_changed=lambda: None,  # captura via var do widget
        )
        self._controls.grid(row=1, column=0, sticky="ew")

        # Linha 2: Conteúdo principal (Transcrição + Painel lateral)
        content = ctk.CTkFrame(self._root, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._transcription = TranscriptionPanel(
            content,
            on_copy=self._on_copy,
            on_save=self._on_save,
            on_export=self._on_export,
            on_clear=self._on_clear,
        )
        self._transcription.grid(row=0, column=0, sticky="nsew")

        self._results = ResultsPanel(
            content,
            on_summarize=self._on_summarize,
            on_answer=self._on_answer,
            on_set_context=self._on_set_context,
            on_translate=self._on_translate,
            on_reprocess=self._on_reprocess_diarization,
            on_speaker_map_changed=self._save_speaker_map,
            get_llm_config=self._get_llm_config_for_dialog,
            on_save_llm=self._on_save_llm_config,
            on_test_llm=self._on_test_llm,
        )
        # Painel lateral: coluna 1, largura fixa via grid_propagate(False) no ResultsPanel
        self._results.grid(row=0, column=1, sticky="ns")
        self._results.grid_remove()  # começa recolhido

        # Linha 3: Toast
        self._toast = Toast(self._root)
        self._toast.grid(row=3, column=0, sticky="ew")

        # Linha 4: Status bar
        self._statusbar = StatusBar(self._root, on_open_folder=self._on_open_folder)
        self._statusbar.grid(row=4, column=0, sticky="ew")

    # -------------------------------------------------------------------------
    # Atalhos de teclado
    # -------------------------------------------------------------------------

    def _bind_shortcuts(self):
        for bind, action in SHORTCUTS.items():
            self._root.bind(bind, lambda e, a=action: self._dispatch_shortcut(a))

    def _dispatch_shortcut(self, action: str):
        if action == "toggle_recording":
            self._on_toggle_recording()
        elif action == "save_transcription":
            self._on_save(self._transcription.get_text())
        elif action == "clear_transcription":
            self._on_clear(self._transcription)
        elif action == "open_settings":
            self._open_settings()
        elif action == "close_secondary":
            # Fecha dialog se aberto, senão painel lateral
            if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
                self._settings_dialog.close()
            elif self._results.is_open:
                self._results.close()

    # -------------------------------------------------------------------------
    # Tema
    # -------------------------------------------------------------------------

    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        mode = "dark" if self._is_dark else "light"
        ctk.set_appearance_mode(mode)
        self._header.set_theme_label(self._is_dark)
        config_store.set("theme", mode)

    # -------------------------------------------------------------------------
    # Settings Dialog
    # -------------------------------------------------------------------------

    def _open_settings(self):
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog.focus_set()
            return

        self._settings_dialog = SettingsDialog(
            self._root,
            caps=self._caps,
            on_theme_change=self._on_theme_change_dialog,
            on_scaling_change=self._on_scaling_change_dialog,
            on_prefix_change=self._on_prefix_change_dialog,
            on_select_region=self._on_select_region,
            on_ocr_start=self._on_ocr_start,
            on_ocr_stop=self._on_ocr_stop,
            llm_config_provider=self._get_llm_config_for_dialog,
            on_save_llm=self._on_save_llm_config,
            on_test_llm=self._on_test_llm,
        )

    def _on_theme_change_dialog(self, mode: str):
        self._is_dark = (mode == "dark")
        ctk.set_appearance_mode(mode)
        self._header.set_theme_label(self._is_dark)
        config_store.set("theme", mode)

    def _on_scaling_change_dialog(self, factor: float):
        config_store.set("ui_scaling", factor)
        # Atualiza nota no dialog
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog._update_scale_note(factor)

    def _on_prefix_change_dialog(self, prefix: str):
        # persistido ao fechar? persistir imediatamente
        config_store.set("last_prefix", prefix)

    def _get_llm_config_for_dialog(self, provider: str) -> dict:
        # provider="" significa "dá-me o config completo com active_provider"
        if not provider:
            return config_store.get_llm_config()
        return config_store.get_llm_provider_config(provider)

    def _on_save_llm_config(self, provider: str, fields: dict):
        config_store.set_llm_provider_config(provider, fields)
        llm_cfg = config_store.get_llm_config()
        llm_cfg["active_provider"] = provider
        config_store.set_llm_config(llm_cfg)
        if not llm_manager._initialized:
            llm_manager.initialize()
        llm_manager.switch_provider(provider, fields)
        self._update_provider_labels()

    def _on_test_llm(self, callback):
        # rodar em thread
        def task():
            try:
                result = llm_manager.generate("Say 'connection ok' and nothing else.", max_tokens=10)
                success = "Erro" not in result and "connection ok" in result.lower()[:20]
                self._root.after(0, lambda: callback(success, result))
            except Exception as e:  # noqa: F841
                self._root.after(0, lambda: callback(False, str(e)))  # noqa: F821
        threading.Thread(target=task, daemon=True).start()

    # -------------------------------------------------------------------------
    # Seleção de região (OCR)
    # -------------------------------------------------------------------------

    def _on_select_region(self):
        selector = RegionSelector()
        region = selector.select()
        if region:
            settings.screen_region = region
            config_store.set_region(region)
            # Atualiza label no dialog se aberto
            if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
                self._settings_dialog._region_lbl.configure(
                    text=f"Região: top={region['top']}, left={region['left']}, width={region['width']}, height={region['height']}"
                )
        return region

    # -------------------------------------------------------------------------
    # Fluxo OCR (SessionManager) — preservado em SettingsDialog
    # -------------------------------------------------------------------------

    def _on_ocr_start(self, prefix: str, activate: bool) -> str:
        msg = self.session.start(prefix, activate)
        if "Erro" in msg:
            return msg
        # Atualizar botões no dialog
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog._btn_ocr_start.configure(state="disabled")
            self._settings_dialog._btn_ocr_stop.configure(state="normal")
        return msg

    def _on_ocr_stop(self) -> str:
        msg = self.session.stop()
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog._btn_ocr_start.configure(state="normal")
            self._settings_dialog._btn_ocr_stop.configure(state="disabled")
        return msg

    # -------------------------------------------------------------------------
    # Callbacks SessionManager (OCR)
    # -------------------------------------------------------------------------

    def _on_captured(self, text: str):
        # OCR capturado → transcrição principal + feed session para resumo/resposta
        self._root.after(0, lambda: self._transcription.append_line(text))
        self._session_feed_audio_line(text)

    def _on_translated(self, original: str, translated: str):
        self._root.after(0, lambda: self._results.append_translation(translated))

    def _on_question(self, text: str):
        self._root.after(0, lambda: self._toast.show(
            f"🔔 Pergunta detectada: {text[:120]} — gere uma resposta no painel (Responder).",
            kind="question",
            sticky=True,
        ))

    # -------------------------------------------------------------------------
    # Dispositivos de áudio
    # -------------------------------------------------------------------------

    def _refresh_audio_devices(self):
        devices = self._audio_manager.list_devices()
        if not devices:
            msg = "Nenhum dispositivo PipeWire encontrado"
            self._controls.set_devices([msg])
            self._controls.set_error(msg)
            return

        self._audio_devices_meta = []
        labels = []
        for d in devices:
            backend_id = d.get("_backend_id", str(d["index"]))
            kind = d.get("kind", "input")
            label = d["name"]
            if kind == "monitor":
                label = f"🔊 {label}  (áudio do sistema)"
            elif kind == "input":
                label = f"🎤 {label}"
            else:
                label = f"🎧 {label}"
            labels.append(label)
            self._audio_devices_meta.append({
                "label": label,
                "backend_id": backend_id,
                "kind": kind,
                "name": d["name"],
                "index": d["index"],
            })
        self._controls.set_devices(labels)
        self._controls.clear_error()
        self._update_statusbar_source()

    def _resolve_backend_id(self, selected_label: str) -> int | str | None:
        for meta in self._audio_devices_meta:
            if meta["label"] == selected_label:
                return meta["backend_id"]
        # Fallback legacy: "idx: name"
        if ":" in selected_label:
            try:
                return int(selected_label.split(":")[0])
            except ValueError:
                return None
        return None

    def _update_statusbar_source(self):
        label = self._controls.selected_device()
        model = settings.stt_model
        backend = "PipeWire" if self._caps.is_linux else "WASAPI"
        self._statusbar.set_source(label, model, backend)

    # -------------------------------------------------------------------------
    # Gravação (AudioManager) — fluxo principal
    # -------------------------------------------------------------------------

    def _on_toggle_recording(self):
        state = self._machine.state
        if state == RecordingState.IDLE:
            self._start_recording()
        elif state == RecordingState.RECORDING:
            self._stop_recording()
        # STARTING/STOPPING ignoram

    def _start_recording(self):
        # Validar dispositivo
        devices = self._audio_manager.list_devices()
        if not devices:
            self._toast.show("Nenhum dispositivo de áudio disponível.", kind="error")
            self._controls.set_error("Nenhum dispositivo PipeWire/PulseAudio")
            return

        backend_id = self._resolve_backend_id(self._controls.selected_device())
        if backend_id is None:
            self._controls.set_error("Dispositivo selecionado inválido")
            self._toast.show("Dispositivo inválido.", kind="error")
            return

        try:
            self._machine.transition(RecordingState.STARTING)
        except Exception:
            return

        self._controls.apply_state(self._machine)
        self._header.set_status(self._machine.status_text, self._machine.status_kind)
        self._controls.clear_error()

        # Iniciar AudioManager
        try:
            self._audio_manager.start(
                device_index=backend_id,
                enable_diarization=self._controls.diarize_enabled(),
            )
        except Exception as e:
            self._machine.transition(RecordingState.IDLE)
            self._controls.apply_state(self._machine)
            self._header.set_status("Erro ao iniciar", "error")
            self._controls.set_error(f"Erro: {e}")
            self._toast.show(f"Erro ao iniciar captura: {e}", kind="error")
            return

        # Sucesso
        self._machine.transition(RecordingState.RECORDING)
        self._controls.apply_state(self._machine)
        self._header.set_status(self._machine.status_text, self._machine.status_kind)

        # Estado inicial
        self._audio_transcript_lines.clear()
        self._transcription.clear()  # limpa e mostra placeholder "Gravando..."
        self._transcription.set_export_enabled(False)
        self._results.set_reprocess_enabled(False)

        # Timer
        self._record_started_at = time.monotonic()
        self._tick_timer()

        # Status bar
        self._statusbar.set_file(None)

    def _stop_recording(self):
        try:
            self._machine.transition(RecordingState.STOPPING)
        except Exception:
            return

        self._controls.apply_state(self._machine)
        self._header.set_status(self._machine.status_text, self._machine.status_kind)

        self._audio_manager.stop()

        self._machine.transition(RecordingState.IDLE)
        self._controls.apply_state(self._machine)
        self._header.set_status(self._machine.status_text, self._machine.status_kind)
        self._controls.reset_timer()

        # Habilita exportar/reprocessar se houver dados
        if self._audio_manager.recorded_wav:
            self._results.set_reprocess_enabled(True)
        if self._audio_transcript_lines:
            self._transcription.set_export_enabled(True)

        self._toast.show("Gravação finalizada.", kind="ok")

    def _tick_timer(self):
        if self._machine.state != RecordingState.RECORDING:
            return
        elapsed = time.monotonic() - self._record_started_at
        dur = format_duration(elapsed)
        self._controls.set_timer(dur)
        self._header.set_status(f"● Gravando — {dur}", "recording")
        self._root.after(1000, self._tick_timer)

    # -------------------------------------------------------------------------
    # Callbacks AudioManager
    # -------------------------------------------------------------------------

    def _on_audio_transcription(self, text: str, speaker: str | None = None):
        self._save_speaker_map()
        prefix = self._results.get_speaker_display_name(speaker)
        line = f"{prefix}{text}"
        self._audio_transcript_lines.append(line)
        self._root.after(0, lambda: self._transcription.append_line(line))
        self._session_feed_audio_line(line)

    def _on_audio_error(self, error: str):
        self._root.after(0, lambda: self._controls.set_error(f"Erro: {error}"))
        self._root.after(0, lambda: self._toast.show(f"Erro de áudio: {error}", kind="error"))

    def _session_feed_audio_line(self, line: str):
        if hasattr(self.session, "feed_audio_caption"):
            self.session.feed_audio_caption(line)

    # -------------------------------------------------------------------------
    # Ações do painel de transcrição
    # -------------------------------------------------------------------------

    def _on_copy(self, text: str):
        if not text:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(text)
        self._toast.show("✓ Transcrição copiada.", kind="ok")

    def _on_save(self, text: str):
        if not text:
            return
        from pathlib import Path
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = Path(settings.recording_dir) / f"transcricao_{timestamp}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self._toast.show(f"✓ Salvo: {path.name}", kind="ok")

    def _on_export(self):
        from pathlib import Path
        lines = self._audio_transcript_lines
        if not lines:
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = Path(settings.recording_dir) / f"transcricao_{timestamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        translated = None
        try:
            translated = self._results._translation_box.get("1.0", "end").strip()
        except Exception:
            pass

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Transcrição — {timestamp}\n\n")
            f.write("## Transcrição Original\n\n")
            for line in lines:
                f.write(f"- {line}\n")
            if translated:
                f.write("\n## Tradução (PT)\n\n")
                f.write(translated + "\n")
            f.write("\n---\n*Exportado por Gravador de Legendas*\n")

        self._toast.show(f"✓ Exportado: {path.name}", kind="ok")

    def _on_clear(self, panel: TranscriptionPanel):
        if not panel.has_content():
            return
        if not tkmsg.askyesno("Limpar transcrição", "Tem certeza que deseja limpar todo o conteúdo?"):
            return
        panel.clear()
        self._audio_transcript_lines.clear()
        self._toast.show("Transcrição limpa.", kind="ok")

    # -------------------------------------------------------------------------
    # Ações do painel de resultados
    # -------------------------------------------------------------------------

    def _on_translate(self):
        full_text = "\n".join(self._audio_transcript_lines)
        if not full_text:
            self._toast.show("Nada para traduzir.", kind="warn")
            return
        self._results.open("Tradução")
        self._toast.show("Traduzindo…", kind="ok", timeout_ms=1000)

        def task():
            try:
                translated = self._translator_api.translate(full_text)
                self._root.after(0, lambda: self._results.set_translation(translated))
                self._root.after(0, lambda: self._toast.show("✓ Tradução pronta.", kind="ok"))
            except Exception as e:  # noqa: F841
                self._root.after(0, lambda: self._toast.show(f"Erro na tradução: {e}", kind="error"))  # noqa: F821

        threading.Thread(target=task, daemon=True).start()

    def _on_summarize(self, system_prompt: str | None, user_prompt: str | None):
        full_text = self.session.get_full_text()
        if not full_text:
            self._toast.show("Nenhum texto capturado para resumir.", kind="warn")
            return

        self._results.open("Resumo")
        self._results.show_summary_progress(True)

        def task():
            try:
                result = self._summarizer.summarize(
                    text=full_text,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                self._root.after(0, lambda: self._results.show_summary_progress(False))
                self._root.after(0, lambda: self._results.set_summary(result))
                self._root.after(0, lambda: self._toast.show("✓ Resumo gerado.", kind="ok"))
            except Exception as e:  # noqa: F841
                self._root.after(0, lambda: self._results.show_summary_progress(False))
                self._root.after(0, lambda: self._toast.show(f"Erro no resumo: {e}", kind="error"))  # noqa: F821

        threading.Thread(target=task, daemon=True).start()

    def _on_set_context(self, ctx: str) -> bool:
        if not ctx:
            return False
        self.session.context = ctx
        return True

    def _on_answer(self):
        question = self.session.last_question
        if not question:
            self._toast.show("Nenhuma pergunta detectada.", kind="warn")
            return
        if not self.session.context:
            self._toast.show("Defina o contexto primeiro no painel Resposta.", kind="warn")
            return

        self._results.open("Resposta")
        self._toast.show("Gerando resposta…", kind="ok", timeout_ms=1000)

        def task():
            try:
                gen = ManagedGenerator()
                answer = gen.generate(question, self.session.context)
                translated = self.session.translator.translate(answer)
                self._root.after(0, lambda: self._results.set_answer(answer, translated))
                self._root.after(0, lambda: self._toast.show("✓ Resposta gerada.", kind="ok"))
            except Exception as e:  # noqa: F841
                self._root.after(0, lambda: self._toast.show(f"Erro na resposta: {e}", kind="error"))  # noqa: F821

        threading.Thread(target=task, daemon=True).start()

    def _on_reprocess_diarization(self):
        self._toast.show("Re-processando com diarização…", kind="ok", timeout_ms=1000)
        self._results.set_reprocess_enabled(False)

        def task():
            segments = self._audio_manager.reprocess_with_diarization()
            if not segments:
                self._root.after(0, lambda: self._toast.show("Nenhum segmento de diarização gerado.", kind="warn"))
                self._root.after(0, lambda: self._results.set_reprocess_enabled(True))
                return
            existing_speakers = {seg["speaker"] for seg in segments}
            for sid in existing_speakers:
                if sid not in self._results._speaker_rows:
                    self._root.after(0, lambda s=sid: self._results._add_speaker_row(s, s))
            self._root.after(0, lambda: self._toast.show(
                f"✓ Diarização: {len(segments)} segmentos, {len(existing_speakers)} falantes.",
                kind="ok",
            ))
            self._root.after(0, lambda: self._results.set_reprocess_enabled(True))

        threading.Thread(target=task, daemon=True).start()

    # -------------------------------------------------------------------------
    # Speaker map
    # -------------------------------------------------------------------------

    def _save_speaker_map(self):
        mapping = self._results.get_speaker_map()
        config_store.set("speaker_map", mapping)

    # -------------------------------------------------------------------------
    # Provider labels
    # -------------------------------------------------------------------------

    def _update_provider_labels(self):
        text = self._provider_display()
        self._results.set_provider_label(text)
        self._results.set_answer_provider_label(text)

    def _provider_display(self) -> str:
        name = llm_manager.active_provider or "nenhum"
        info = llm_manager.list_providers()
        for p in info:
            if p["name"] == name:
                model = p.get("model", "")
                if model:
                    return f"🤖 {name} · {model}"
                return f"🤖 {name}"
        return f"🤖 {name}"

    # -------------------------------------------------------------------------
    # Folder / fechamento
    # -------------------------------------------------------------------------

    def _on_open_folder(self):
        _open_folder_crossplatform(settings.recording_dir)

    def _on_closing(self):
        _perform_window_close(self, config_store)

    def _load_speaker_map(self):
        """Carrega o speaker map persistido no ResultsPanel."""
        mapping = config_store.get("speaker_map", {})
        apply_speaker_map(self._results, mapping)

    def run(self):
        self._root.mainloop()


def _shutdown(window, store) -> None:
    """Encapsula a lógica de shutdown de MainWindow para testes headless.

    Ordem:
      1. Parar AudioManager se houver captura ativa.
      2. Parar SessionManager/OCR.
      3. Persistir geometria da janela.
    """
    if window._audio_manager.is_running:
        window._audio_manager.stop()
    window.session.stop()
    geometry = window._root.geometry()
    store.set("window_geometry", geometry)


def _perform_window_close(window, store) -> bool:
    """Fecha a janela de forma idempotente.

    Returns:
        True se executou o shutdown/destruição; False se já estava fechando.
    """
    if window._closing:
        return False
    window._closing = True
    try:
        _shutdown(window, store)
    finally:
        window._root.destroy()
    return True
