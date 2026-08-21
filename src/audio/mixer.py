"""Mixagem de dois streams PCM em um único stream.

Frente B do plano de curto prazo: implementar de fato o
``audio_source=both`` (hoje apenas validado em ``validate_settings()``
mas não implementado no ``AudioManager``).

A mixagem é uma soma simples normalizada em domínio float32 com clamp,
precedida por um AGC muito conservador: cada trilho é normalizado para
um RMS-alvo comum **antes** de somar, para evitar o cenário do teste
T4.2 (uma fonte "engolindo" a outra por diferença de volume).

Quando uma das fontes está ausente (silêncio puro / None), o mixer
simplesmente repassa a outra sem degradar o sinal (cobre T4.3).
"""
from __future__ import annotations

import struct
import threading

import numpy as np
import structlog

_logger = structlog.get_logger()

# RMS-alvo em float32 [-1.0, 1.0]. ~0.05 corresponde a ~-26 dBFS, um
# nível confortável para voz. Não very agressivo: se o sinal já está
# acima do alvo, o ganho é limitado a 1.0 (não ampliamos saturação).
_DEFAULT_TARGET_RMS = 0.05
# Limiar para considerar um frame como silêncio (não aplicar AGC).
_SILENCE_RMS = 0.001


class AudioMixer:
    """Combina dois streams PCM s16le em um único stream s16le mono.

    Args:
        sample_rate: Taxa de amostragem (Hz). Default 16000.
        channels: Número de canais (sempre 1 no pipeline).
        target_rms: RMS-alvo em float32 para o AGC pré-mixagem.
            Default 0.05 (~-26 dBFS). Se None, desativa AGC.

    Example:
        >>> mixer = AudioMixer(sample_rate=16000)
        >>> out = mixer.mix_frame(mic_bytes, system_bytes)
        >>> len(out) == max(len(mic_bytes), len(system_bytes))
        True
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        target_rms: float | None = _DEFAULT_TARGET_RMS,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.target_rms = target_rms
        self._lock = threading.Lock()

    def mix_frame(
        self,
        frame_mic: bytes | None,
        frame_sistema: bytes | None,
    ) -> bytes:
        """Combina dois frames PCM s16le em um único frame PCM s16le.

        - Se ambos forem None/vazios: retorna bytes vazios.
        - Se apenas um for None/vazio: retorna o outro **sem** aplicar
          AGC (sinal intocado — cobre T4.3).
        - Se ambos presentes: aplica AGC a cada um (normalização para
          ``target_rms``), soma, clamp para [-1.0, 1.0], reconverte
          para int16.

        Args:
            frame_mic: Chunk PCM s16le do microfone (pode ser None).
            frame_sistema: Chunk PCM s16le do sistema (pode ser None).

        Returns:
            Chunk PCM s16le mono, mesmo tamanho do maior frame de entrada.
        """
        # Caso trivial: nenhum sinal
        if not frame_mic and not frame_sistema:
            return b""

        # Caso T4.3: apenas uma fonte — repassar sem processar
        if not frame_mic:
            return bytes(frame_sistema)
        if not frame_sistema:
            return bytes(frame_mic)

        with self._lock:
            return self._mix_both(frame_mic, frame_sistema)

    def _mix_both(self, frame_mic: bytes, frame_sistema: bytes) -> bytes:
        """Soma normalizada de dois frames não-vazios."""
        # Trunca bytes ímpares (sample PCM s16le incompleto).
        if len(frame_mic) % 2 != 0:
            frame_mic = frame_mic[:-1]
        if len(frame_sistema) % 2 != 0:
            frame_sistema = frame_sistema[:-1]
        if not frame_mic or not frame_sistema:
            # Após truncagem um dos frames ficou vazio — cai no caso T4.3.
            if not frame_mic:
                return bytes(frame_sistema)
            return bytes(frame_mic)

        # Padding do menor para igualar tamanho
        size = max(len(frame_mic), len(frame_sistema))
        mic_padded = frame_mic.ljust(size, b"\x00")
        sys_padded = frame_sistema.ljust(size, b"\x00")

        # s16le -> float32
        a = np.frombuffer(mic_padded, dtype=np.int16).astype(np.float32) / 32768.0
        b = np.frombuffer(sys_padded, dtype=np.int16).astype(np.float32) / 32768.0

        # AGC: normalizar cada trilho para target_rms, limitando ganho
        # a 1.0 (não amplificar saturação) e não mexer em silêncio.
        a = self._agc(a)
        b = self._agc(b)

        # Soma normalizada: (a+b)/2 + clamp para evitar overflow
        mixed = (a + b) * 0.5
        mixed = np.clip(mixed, -1.0, 1.0)

        # float32 -> s16le
        return (mixed * 32767.0).astype(np.int16).tobytes()

    def _agc(self, x: np.ndarray) -> np.ndarray:
        """Aplica ganho automático para aproximar ``target_rms``.

        - Se ``target_rms`` é None, retorna x inalterado.
        - Se o frame é silêncio (RMS < _SILENCE_RMS), retorna x inalterado.
        - Caso contrário, ganho = min(target_rms / rms, 1.0). O limite
          superior 1.0 garante que nunca amplificamos um sinal já alto.
        """
        if self.target_rms is None or x.size == 0:
            return x
        rms = float(np.sqrt(np.mean(x ** 2)))
        if rms < _SILENCE_RMS:
            return x
        gain = min(self.target_rms / rms, 1.0)
        return x * gain
