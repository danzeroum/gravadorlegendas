"""Captura de áudio — fachada retrocompatível.

Historicamente este módulo implementava diretamente WASAPI loopback
(PyAudio) e era Windows-only. A partir da migração Linux/Fedora, ele
passa a ser uma fachada fina que delega para o backend apropriado
(``WasapiLoopbackCapture`` em Windows, ``PipewireCapture`` em Linux),
selecionado automaticamente por ``src.audio.backends.factory``.

A API pública (métodos ``list_devices``, ``start``, ``stop`` e o
atributo ``device_index``) é preservada para que ``AudioManager`` e os
testes existentes continuem funcionando sem mudanças.
"""
from __future__ import annotations

import logging

from src.audio.backends import build_audio_backend, AudioBackendError
from src.platform.types import AudioCaptureConfig

_logger = logging.getLogger(__name__)


class AudioCapture:
    """Fachada retrocompatível para captura de áudio.

    Attributes:
        device_index: Identificador do dispositivo (legado: índice WASAPI;
            novo: também aceita string com ID PipeWire). Aceita int ou str.
        sample_rate: Taxa de amostragem (Hz).
        channels: Número de canais (sempre 1 — mono).
        chunk_size: Tamanho do chunk em frames.
    """

    def __init__(
        self,
        device_index: int | str | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 480,
        backend: str = "auto",
    ) -> None:
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = 1
        self.chunk_size = chunk_size
        self._backend_name = backend
        self._backend = None  # construído lazy no primeiro start/list

    def _build_backend(self):
        if self._backend is not None:
            return self._backend
        try:
            self._backend = build_audio_backend(
                requested=self._backend_name,
                device_id=self.device_index,
                sample_rate=self.sample_rate,
                chunk_size=self.chunk_size,
            )
        except AudioBackendError as e:
            _logger.error("Falha ao construir backend de áudio: %s", e)
            # Backend nulo — list_devices retorna [] e start registra erro.
            self._backend = None
        return self._backend

    def list_devices(self) -> list[dict]:
        """Lista dispositivos disponíveis no backend ativo.

        Returns:
            Lista de dicts com 'index', 'name', 'channels', 'rate',
            'is_loopback' — formato preservado para compatibilidade com
            a UI e com os testes existentes.
        """
        backend = self._build_backend()
        if backend is None:
            return []
        devices = backend.list_devices()
        out: list[dict] = []
        for i, d in enumerate(devices):
            out.append({
                "index": i,
                # ID estável do backend guardado em '_backend_id' para
                # o start() poder usar.
                "_backend_id": d.id,
                "name": d.name,
                "channels": d.channels,
                "rate": d.sample_rate,
                "is_loopback": d.kind in ("monitor", "output"),
                "kind": d.kind,
                "backend": d.backend,
            })
        return out

    def start(self, output_queue) -> None:
        """Inicia captura em thread separada.

        Args:
            output_queue: Queue onde chunks de áudio PCM s16le são enviados.
        """
        backend = self._build_backend()
        if backend is None:
            _logger.error(
                "Nenhum backend de áudio disponível. start() ignorado."
            )
            return
        config = AudioCaptureConfig(
            device_id=str(self.device_index) if self.device_index is not None else None,
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_frames=self.chunk_size,
        )
        backend.start(config, output_queue)

    def stop(self) -> None:
        """Para a captura."""
        if self._backend is not None:
            self._backend.stop()

    @property
    def is_running(self) -> bool:
        if self._backend is None:
            return False
        return self._backend.is_running
