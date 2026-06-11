"""Módulo de captura de tela.

Fornece a classe ScreenCapture para capturar regiões da tela
e pré-processar imagens para OCR.
"""
from threading import Lock
from PIL import Image, ImageOps
from mss import mss


class ScreenCapture:
    """Captura uma região da tela usando mss.

    Attributes:
        region: Dicionário com top, left, width, height da região.
    """

    def __init__(self, region: dict):
        """Inicializa com a região de captura.

        Args:
            region: Dict com chaves 'top', 'left', 'width', 'height'.
        """
        self._region = region
        self._lock = Lock()

    @property
    def region(self) -> dict:
        """Retorna a região atual de captura."""
        return self._region

    @region.setter
    def region(self, value: dict):
        """Define uma nova região de captura (thread-safe)."""
        with self._lock:
            self._region = value

    def capture(self) -> Image.Image:
        """Captura um frame da região configurada.

        Returns:
            Imagem PIL RGB da região capturada.
        """
        with self._lock:
            with mss() as sct:
                screenshot = sct.grab(self._region)
                return Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    @staticmethod
    def preprocess(img: Image.Image, invert_dark: bool = True) -> Image.Image:
        """Pré-processa a imagem para melhorar a qualidade do OCR.

        Converte para escala de cinza, inverte se o fundo for escuro
        e binariza com limiar adaptativo.

        Args:
            img: Imagem PIL de entrada.
            invert_dark: Se True, inverte cores quando o fundo é escuro.

        Returns:
            Imagem binária em escala de cinza pronta para OCR.
        """
        img = img.convert("L")
        if invert_dark:
            extrema = img.getextrema()
            if extrema[1] < 128:
                img = ImageOps.invert(img)
        img = img.point(lambda x: 0 if x < 140 else 255)
        return img
