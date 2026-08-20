"""Fonte: transcrição local (faster-whisper).

Esta fonte é a padrão em Linux. Em Windows, pode ser usada quando o
usuário prefere não depender das Legendas ao Vivo.

A classe é um invólucro fino sobre ``src.audio.manager.AudioManager``:
ela apenas expõe o ciclo de vida start/stop e encaminha transcrições
via callback. Toda a lógica de VAD / buffer / diarização permanece
em ``src.audio`` — não há duplicação.
"""
from __future__ import annotations

from typing import Callable, Optional

from src.caption.base import CaptionSourceBase, CaptionSourceError


class LocalSTTSource(CaptionSourceBase):
    """Fonte de legendas baseada em transcrição local de áudio.

    Args:
        audio_manager: Instância de ``AudioManager`` (já configurada
            com dispositivo e callbacks). Se None, será criada no
            ``_start()``.
        on_transcription: Callback(text, speaker) chamado a cada
            segmento transcrito.
        on_error: Callback(str) chamado em erros.
        device_index: Índice do dispositivo (None = auto-detect).
        enable_diarization: Se True, ativa diarização em tempo real.
    """

    def __init__(
        self,
        audio_manager=None,
        on_transcription: Optional[Callable[[str, Optional[str]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        device_index: Optional[int] = None,
        enable_diarization: bool = True,
    ) -> None:
        super().__init__(name="local_stt")
        self._audio_manager = audio_manager
        self._on_transcription = on_transcription
        self._on_error = on_error
        self._device_index = device_index
        self._enable_diarization = enable_diarization
        self._owns_manager = audio_manager is None

    def _ensure_manager(self):
        if self._audio_manager is not None:
            return
        try:
            from src.audio.manager import AudioManager
        except ImportError as e:  # pragma: no cover
            raise CaptionSourceError(
                f"AudioManager indisponível: {e}. Instale com "
                "'pip install -e .[audio]'."
            ) from e
        self._audio_manager = AudioManager()

    def _start(self) -> None:
        self._ensure_manager()
        assert self._audio_manager is not None
        if self._on_transcription:
            self._audio_manager.on_transcription = self._on_transcription
        if self._on_error:
            self._audio_manager.on_error = self._on_error
        try:
            self._audio_manager.start(
                device_index=self._device_index,
                enable_diarization=self._enable_diarization,
            )
        except Exception as e:
            raise CaptionSourceError(
                f"Falha ao iniciar AudioManager: {e}"
            ) from e

    def _stop(self) -> None:
        if self._audio_manager is None:
            return
        try:
            self._audio_manager.stop()
        except Exception as e:  # pragma: no cover
            raise CaptionSourceError(f"Erro ao parar AudioManager: {e}") from e

    @property
    def audio_manager(self):
        """Expõe o AudioManager para acesso pela UI (lista de dispositivos, etc.)."""
        return self._audio_manager
