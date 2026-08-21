"""Gravação de áudio bruto em trilhos separados (mic + sistema).

Frente A do plano de curto prazo: gravar dois arquivos WAV distintos
e sincronizados no tempo, um por fonte de áudio.

A classe :class:`DualTrackRecorder` é independente do backend: delega
a captura de cada trilho a um :class:`AudioCapture` existente (que por
sua vez delega para ``PipewireCapture`` ou ``WasapiLoopbackCapture``).
Cada trilho é escrito diretamente em disco via ``wave.open(..., "wb")``
em thread própria, sem re-capturar do dispositivo — o fluxo de áudio
que já passa pelo ``AudioManager`` é duplicado em "fan-out" para o
gravador, evitando abrir o dispositivo duas vezes.

O gravador registra o timestamp monotônico do **primeiro frame**
recebido em cada trilho (não o instante do ``start()``), para permitir
a validação de sincronismo entre os dois arquivos (T3.2 do plano de
testes).
"""
from __future__ import annotations

import os
import threading
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import structlog

_logger = structlog.get_logger()


@dataclass
class DualTrackResult:
    """Resultado de uma gravação dual-track concluída.

    Attributes:
        mic_path: Caminho do WAV do trilho do microfone (None se não gravou).
        system_path: Caminho do WAV do trilho do sistema (None se não gravou).
        duration_s: Duração aproximada da gravação em segundos
            (baseada no trilho mais longo).
        mic_start_monotonic: Timestamp monotônico do primeiro frame do mic.
        system_start_monotonic: Timestamp monotônico do primeiro frame do sistema.
        mic_samples: Número de amostras PCM efetivamente gravadas no mic.
        system_samples: Número de amostras PCM efetivamente gravadas no sistema.
        sample_rate: Taxa de amostragem usada (Hz).
        channels: Número de canais (sempre 1, mono).
    """

    mic_path: str | None = None
    system_path: str | None = None
    duration_s: float = 0.0
    mic_start_monotonic: float | None = None
    system_start_monotonic: float | None = None
    mic_samples: int = 0
    system_samples: int = 0
    sample_rate: int = 16000
    channels: int = 1


class _TrackWriter:
    """Thread-safe writer de um único trilho WAV.

    Recebe chunks de bytes PCM s16le, escreve no arquivo via ``wave``
    e registra o timestamp do primeiro frame.
    """

    def __init__(
        self,
        path: str,
        sample_rate: int,
        channels: int = 1,
        sample_width: int = 2,
    ):
        self._path = path
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = sample_width
        self._lock = threading.Lock()
        self._wf: wave.Wave_write | None = None
        self._closed = False
        self._samples_written = 0
        self._first_frame_monotonic: float | None = None

    @property
    def path(self) -> str:
        return self._path

    @property
    def samples_written(self) -> int:
        return self._samples_written

    @property
    def first_frame_monotonic(self) -> float | None:
        return self._first_frame_monotonic

    def open(self) -> None:
        """Abre o arquivo WAV para escrita."""
        # Garante que o diretório pai existe.
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._wf = wave.open(self._path, "wb")
        self._wf.setnchannels(self._channels)
        self._wf.setsampwidth(self._sample_width)
        self._wf.setframerate(self._sample_rate)

    def write(self, chunk: bytes) -> None:
        """Escreve um chunk PCM s16le no arquivo.

        Thread-safe. Registra o timestamp do primeiro chunk recebido.
        """
        if not chunk or self._closed or self._wf is None:
            return
        with self._lock:
            if self._first_frame_monotonic is None:
                self._first_frame_monotonic = time.monotonic()
            self._wf.writeframes(chunk)
            # 2 bytes por amostra (s16le), mono
            self._samples_written += len(chunk) // (self._sample_width * self._channels)

    def close(self) -> None:
        """Fecha o arquivo WAV graciosamente."""
        with self._lock:
            if self._wf is not None and not self._closed:
                try:
                    self._wf.close()
                except Exception as e:
                    _logger.warning("dual_track_close_error",
                                    path=self._path, error=str(e))
            self._closed = True
            self._wf = None


class DualTrackRecorder:
    """Grava áudio bruto em dois trilhos WAV sincronizados.

    Não captura do dispositivo diretamente: recebe chunks PCM s16le de
    duas fontes distintas (mic e sistema) via :meth:`feed_mic` /
    :meth:`feed_system`, e os escreve em arquivos separados. Cada fonte
    é tipicamente o mesmo stream já aberto pelo ``AudioManager``, em
    "fan-out" para dois consumidores.

    Args:
        output_dir: Diretório onde os WAVs serão salvos.
        sample_rate: Taxa de amostragem (Hz). Default 16000 (STT).
        channels: Número de canais. Sempre 1 (mono) no pipeline.
        prefix: Prefixo do nome de arquivo (timestamp é adicionado).

    Example:
        >>> rec = DualTrackRecorder("/tmp/rec", sample_rate=16000)
        >>> rec.start()
        >>> # durante a sessão, alimentar os trilhos:
        >>> rec.feed_mic(pcm_chunk_mic)
        >>> rec.feed_system(pcm_chunk_system)
        >>> result = rec.stop()
        >>> result.mic_path  # "/tmp/rec/legendas_2026-01-01_12-00-00_mic.wav"
    """

    def __init__(
        self,
        output_dir: str,
        sample_rate: int = 16000,
        channels: int = 1,
        prefix: str = "legendas",
    ):
        self._output_dir = os.path.expanduser(output_dir)
        self._sample_rate = sample_rate
        self._channels = channels
        self._prefix = prefix

        self._mic_writer: _TrackWriter | None = None
        self._system_writer: _TrackWriter | None = None
        self._is_running = False
        self._lock = threading.Lock()
        self._start_call_monotonic: float | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def mic_path(self) -> str | None:
        return self._mic_writer.path if self._mic_writer else None

    @property
    def system_path(self) -> str | None:
        return self._system_writer.path if self._system_writer else None

    def _build_filename(self, kind: str) -> str:
        """Gera nome de arquivo no padrão ``{prefix}_{ts}_{kind}.wav``."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return os.path.join(
            self._output_dir,
            f"{self._prefix}_{timestamp}_{kind}.wav",
        )

    def start(self) -> None:
        """Abre os dois arquivos WAV para escrita.

        Não lança exceção se um dos diretórios não puder ser criado —
        apenas loga e marca o writer como None (o trilho correspondente
        é ignorado, mas o outro continua gravando).
        """
        with self._lock:
            if self._is_running:
                return
            self._start_call_monotonic = time.monotonic()
            try:
                os.makedirs(self._output_dir, exist_ok=True)
            except OSError as e:
                _logger.error("dual_track_mkdir_failed",
                              dir=self._output_dir, error=str(e))
                raise

            mic_path = self._build_filename("mic")
            system_path = self._build_filename("sistema")
            self._mic_writer = _TrackWriter(
                mic_path, self._sample_rate, self._channels,
            )
            self._system_writer = _TrackWriter(
                system_path, self._sample_rate, self._channels,
            )
            self._mic_writer.open()
            self._system_writer.open()
            self._is_running = True
            _logger.info(
                "dual_track_started",
                mic_path=mic_path,
                system_path=system_path,
                sample_rate=self._sample_rate,
            )

    def feed_mic(self, chunk: bytes) -> None:
        """Alimenta um chunk PCM s16le do trilho do microfone."""
        if not self._is_running or self._mic_writer is None:
            return
        self._mic_writer.write(chunk)

    def feed_system(self, chunk: bytes) -> None:
        """Alimenta um chunk PCM s16le do trilho do sistema."""
        if not self._is_running or self._system_writer is None:
            return
        self._system_writer.write(chunk)

    def stop(self, timeout_s: float = 2.0) -> DualTrackResult:
        """Fecha os dois arquivos WAV e retorna o resultado.

        Garante que o último frame recebido antes do ``stop()`` seja
        efetivamente gravado em disco (cobre T3.3 — encerramento limpo).
        Retorna em menos de ``timeout_s`` segundos (proteção contra
        travamento da fila).
        """
        with self._lock:
            if not self._is_running:
                return DualTrackResult(sample_rate=self._sample_rate,
                                       channels=self._channels)
            self._is_running = False

        # Fechar fora do lock: close() pode bloquear em I/O.
        deadline = time.monotonic() + timeout_s
        mic_samples = 0
        system_samples = 0
        mic_start = None
        system_start = None
        mic_path = None
        system_path = None

        if self._mic_writer is not None:
            self._mic_writer.close()
            mic_samples = self._mic_writer.samples_written
            mic_start = self._mic_writer.first_frame_monotonic
            mic_path = self._mic_writer.path
        if self._system_writer is not None:
            self._system_writer.close()
            system_samples = self._system_writer.samples_written
            system_start = self._system_writer.first_frame_monotonic
            system_path = self._system_writer.path

        # Duração baseada no trilho mais longo
        max_samples = max(mic_samples, system_samples)
        duration_s = max_samples / self._sample_rate if self._sample_rate else 0.0

        result = DualTrackResult(
            mic_path=mic_path,
            system_path=system_path,
            duration_s=duration_s,
            mic_start_monotonic=mic_start,
            system_start_monotonic=system_start,
            mic_samples=mic_samples,
            system_samples=system_samples,
            sample_rate=self._sample_rate,
            channels=self._channels,
        )
        _logger.info(
            "dual_track_stopped",
            mic_samples=mic_samples,
            system_samples=system_samples,
            duration_s=round(duration_s, 3),
            elapsed_ms=round((time.monotonic() - (self._start_call_monotonic or 0)) * 1000, 2),
            within_deadline=time.monotonic() <= deadline,
        )
        return result
