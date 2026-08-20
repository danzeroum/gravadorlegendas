"""Módulo de captura de tela.

Fornece a classe ScreenCapture para capturar regiões da tela
e pré-processar imagens para OCR.

Em Wayland, ``mss`` retorna frames pretos (por segurança do compositor).
Nesse caso, ``capture()`` lança ``ScreenCaptureError`` com mensagem
orientando o usuário a usar X11 ou ativar o portal.
"""
from __future__ import annotations

from threading import Lock

from PIL import Image, ImageOps

from src.platform.detection import detect_capabilities, detect_session_type


class ScreenCaptureError(RuntimeError):
    """Erro de captura de tela — geralmente relacionado a Wayland."""


class ScreenCapture:
    """Captura uma região da tela usando mss.

    Attributes:
        region: Dicionário com top, left, width, height da região.
    """

    def __init__(self, region: dict):
        self._region = region
        self._lock = Lock()
        self._session = detect_session_type()
        self._caps = detect_capabilities()
        # Validação inicial: se Wayland sem portal, já alerta.
        if self._session.value == "wayland" and not self._caps.supports_screen_capture:
            import warnings
            warnings.warn(
                "Captura de tela em Wayland não é suportada via mss. "
                "Use sessão X11 ou ative xdg-desktop-portal.",
                stacklevel=2,
            )

    @property
    def region(self) -> dict:
        return self._region

    @region.setter
    def region(self, value: dict):
        with self._lock:
            self._region = value

    def capture(self) -> Image.Image:
        """Captura um frame da região configurada.

        Returns:
            Imagem PIL RGB da região capturada.

        Raises:
            ScreenCaptureError: Se a sessão é Wayland sem portal, ou se
                o frame retornado for totalmente preto (sintoma de
                proteção do compositor).
        """
        # Bloqueio explícito em Wayland sem portal — não devolver frame preto.
        if self._session.value == "wayland" and not self._caps.supports_screen_capture:
            raise ScreenCaptureError(
                "Captura de tela não suportada em Wayland via mss. "
                "Faça logout e entre em sessão Xorg, ou instale "
                "xdg-desktop-portal com suporte a ScreenCast."
            )
        with self._lock:
            from mss import mss
            with mss() as sct:
                screenshot = sct.grab(self._region)
                img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                # Validação: frame totalmente preto em X11/Windows é
                # altamente suspeito — pode ser monitor desligado ou
                # proteção gráfica. Em Wayland é esperado (não deveria
                # chegar aqui, mas defending in depth).
                extrema = img.convert("L").getextrema()
                if extrema == (0, 0):
                    raise ScreenCaptureError(
                        "Frame capturado é totalmente preto. Possível "
                        "limitação de Wayland sem portal ou monitor desligado."
                    )
                return img

    @staticmethod
    def preprocess(img: Image.Image, invert_dark: bool = True) -> Image.Image:
        """Pré-processa a imagem para melhorar a qualidade do OCR.

        Converte para escala de cinza, inverte se o fundo for escuro
        e binariza com limiar adaptativo.
        """
        img = img.convert("L")
        if invert_dark:
            extrema = img.getextrema()
            if extrema[1] < 128:
                img = ImageOps.invert(img)
        img = img.point(lambda x: 0 if x < 140 else 255)
        return img
