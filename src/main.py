"""Orquestração principal do assistente de reunião.

Gerencia o ciclo de vida da captura, processamento e
atualização da interface. A partir da migração Linux/Fedora, o
``SessionManager`` respeita a plataforma:

- Windows: pode usar Legendas ao Vivo do Windows (default) ou
  transcrição local.
- Linux: sempre usa transcrição local ou OCR de tela.
"""
from __future__ import annotations

import logging
import time
import threading
import structlog

from src.config import settings
from src.capture.screen_capture import ScreenCapture, ScreenCaptureError
from src.ocr.engine import OCREngine
from src.translation.marianmt import TranslatorMarianMT
from src.storage.file_manager import FileManager
from src.nlp.question_detector import QuestionDetector
from src.platform.detection import detect_capabilities

_structlog_configured = False
_logger = None


def _configure_structlog() -> None:
    global _structlog_configured, _logger
    if _structlog_configured:
        return
    # Configura logging stdlib primeiro
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _logger = structlog.get_logger()
    _structlog_configured = True


class SessionManager:
    """Gerencia a sessão de captura e processamento.

    Attributes:
        capture: Instância de ScreenCapture.
        ocr: Instância de OCREngine.
        translator: Instância de TranslatorMarianMT.
        file_manager: Instância de FileManager.
        question_detector: Instância de QuestionDetector.
        is_running: Indica se a captura está ativa.
        current_file: Caminho do arquivo atual de gravação.
        last_question: Última pergunta detectada.
    """

    def __init__(self):
        _configure_structlog()
        self._caps = detect_capabilities()
        self.capture = ScreenCapture(settings.screen_region)
        self.ocr = OCREngine()
        self.translator = TranslatorMarianMT()
        self.file_manager = FileManager()
        self.question_detector = QuestionDetector()

        self._is_running = False
        self._captured_texts: set[str] = set()
        self._current_file: str = ""
        self._context: str = ""
        self._last_question: str = ""
        self._thread: threading.Thread | None = None

        self._audio_captions: list[str] = []

        self.on_captured = None
        self.on_translated = None
        self.on_question = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_file(self) -> str:
        return self._current_file

    @property
    def context(self) -> str:
        return self._context

    @context.setter
    def context(self, value: str):
        self._context = value

    @property
    def capabilities(self):
        """Expõe as capacidades detectadas para a UI."""
        return self._caps

    def feed_audio_caption(self, caption: str):
        """Alimenta o session manager com transcrição de áudio com falantes."""
        if caption:
            self._audio_captions.append(caption)

    @property
    def last_question(self) -> str:
        return self._last_question

    def start(self, prefix: str, activate_captions: bool = True) -> str:
        """Inicia a captura de legendas em uma thread separada.

        Args:
            prefix: Prefixo para nomear o arquivo de saída.
            activate_captions: Se True, ativa legendas do Windows
                (apenas em Windows; em Linux é ignorado com aviso).

        Returns:
            Mensagem de status indicando resultado.
        """
        if self._is_running:
            return "Já está gravando."
        if not prefix.strip():
            return "Erro: Prefixo não informado."

        self._current_file = self.file_manager.build_path(prefix)
        self._captured_texts.clear()
        self._is_running = True

        # Ativa Legendas ao Vivo do Windows apenas em Windows.
        if activate_captions and self._caps.supports_windows_live_captions:
            try:
                from src.capture.activate_windows_captions import (
                    activate_windows_captions,
                )
                activate_windows_captions()
            except Exception as e:
                _logger.warning(
                    "activate_windows_captions_failed", error=str(e)
                )
        elif activate_captions and not self._caps.supports_windows_live_captions:
            _logger.info(
                "activate_captions_ignored_on_linux",
                reason="Legendas do Windows não disponíveis nesta plataforma",
            )

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return f"Gravando em: {self._current_file}"

    def stop(self) -> str:
        """Para a captura de legendas."""
        self._is_running = False
        return "Gravação parada."

    def get_full_text(self) -> str:
        """Retorna todo o texto capturado (OCR + áudio) até o momento."""
        parts = []
        if self._current_file:
            try:
                ocr_text = self.file_manager.read_all(self._current_file)
                if ocr_text:
                    parts.append(ocr_text)
            except FileNotFoundError:
                pass
        if self._audio_captions:
            audio_text = "\n".join(self._audio_captions)
            parts.append(f"--- Transcrição de Áudio ---\n{audio_text}")
        return "\n\n".join(parts)

    def _capture_loop(self):
        """Loop principal de captura (executado em thread separada).

        Em Wayland sem portal, captura de tela falha — o loop registra
        erro e aguarda o usuário mudar de sessão. Não derruba a aplicação.
        """
        lang_map = {"eng": "eng", "por": "por", "spa": "spa"}
        ocr_lang = lang_map.get(settings.ocr_language, settings.ocr_language)

        while self._is_running:
            try:
                img = self.capture.capture()
                img = self.capture.preprocess(img)
                text = self.ocr.extract_text(img, lang=ocr_lang)

                if text and text not in self._captured_texts:
                    self._captured_texts.add(text)
                    self.file_manager.save_line(self._current_file, text)

                    if self.on_captured:
                        self.on_captured(text)

                    translated = self.translator.translate(text)
                    if self.on_translated:
                        self.on_translated(text, translated)

                    if self.question_detector.is_question(text):
                        self._last_question = text
                        if self.on_question:
                            self.on_question(text)

            except ScreenCaptureError as e:
                # Wayland sem portal — não tentar capturar repetidamente.
                _logger.error("screen_capture_unavailable", error=str(e))
                if self.on_question:
                    # Reutiliza o canal de notificação para avisar a UI.
                    self.on_question(f"[Captura de tela indisponível: {e}]")
                # Aguarda antes de tentar de novo (evita loop apertado).
                time.sleep(5)
            except Exception as e:
                _logger.error("capture_loop_error", error=str(e))

            time.sleep(1)


def launch_ui() -> None:
    """Ponto de entrada da interface gráfica (``python -m src.main``)."""
    _configure_structlog()
    from src.ui.app import MainWindow

    MainWindow().run()


if __name__ == "__main__":
    launch_ui()
