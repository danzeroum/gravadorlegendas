"""Orquestração principal do assistente de reunião.

Gerencia o ciclo de vida da captura, processamento e
atualização da interface.
"""
import time
import threading

from src.config import settings
from src.capture.screen_capture import ScreenCapture
from src.capture.activate_windows_captions import activate_windows_captions
from src.ocr.engine import OCREngine
from src.translation.marianmt import TranslatorMarianMT
from src.storage.file_manager import FileManager
from src.nlp.question_detector import QuestionDetector


class SessionManager:
    """Gerencia a sessão de captura e processamento.

    Encapsula o loop de captura, tradução, detecção de
    perguntas e notificação da UI. Substitui as variáveis
    globais dos scripts originais.

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

        self.on_captured = None
        self.on_translated = None
        self.on_question = None

    @property
    def is_running(self) -> bool:
        """Indica se a captura está em andamento."""
        return self._is_running

    @property
    def current_file(self) -> str:
        """Caminho do arquivo sendo gravado atualmente."""
        return self._current_file

    @property
    def context(self) -> str:
        """Contexto da reunião definido pelo usuário."""
        return self._context

    @context.setter
    def context(self, value: str):
        """Define o contexto da reunião."""
        self._context = value

    @property
    def last_question(self) -> str:
        """Última pergunta detectada pelo QuestionDetector."""
        return self._last_question

    def start(self, prefix: str, activate_captions: bool = True) -> str:
        """Inicia a captura de legendas em uma thread separada.

        Args:
            prefix: Prefixo para nomear o arquivo de saída.
            activate_captions: Se True, ativa legendas do Windows.

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

        if activate_captions:
            activate_windows_captions()

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return f"Gravando em: {self._current_file}"

    def stop(self) -> str:
        """Para a captura de legendas.

        Returns:
            Mensagem de confirmação.
        """
        self._is_running = False
        return "Gravação parada."

    def get_full_text(self) -> str:
        """Retorna todo o texto capturado até o momento.

        Returns:
            Conteúdo completo do arquivo atual ou string vazia.
        """
        if not self._current_file:
            return ""
        try:
            return self.file_manager.read_all(self._current_file)
        except FileNotFoundError:
            return ""

    def _capture_loop(self):
        """Loop principal de captura (executado em thread separada)."""
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

            except Exception as e:
                print(f"[capture_loop] Erro: {e}")

            time.sleep(1)


if __name__ == "__main__":
    from src.ui.app import MainWindow

    app = MainWindow()
    app.run()
