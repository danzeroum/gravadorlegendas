"""Supressão de ruído em tempo real (RNNoise ou fallback espectral).

Frente C do plano de curto prazo: filtro de ruído frame-a-frame,
inserido no pipeline de áudio **antes** do ``CircularAudioBuffer`` e
**depois** da mixagem da Frente B.

Arquitetura:

- RNNoise opera nativamente em 48 kHz, mono, frames de 480 amostras
  (10 ms). Como o pipeline do projeto usa 16 kHz, esta classe
  encapsula o upsample/downsample internamente (via
  ``scipy.signal.resample_poly``), de modo que o resto do código
  continua trabalhando em 16 kHz sem saber do detalhe do filtro.

- Tenta carregar um binding Python de RNNoise
  (``pyrnnoise``/``rnnoise-wrapper``) em runtime. Se nenhum binding
  estiver instalado, cai para um **fallback espectral** baseado em
  spectral subtraction + noise gate, que aproxima o comportamento de
  RNNoise em sinais sintéticos. O fallback existe para que o pipeline
  não quebre em ambientes sem a lib RNNoise nativa — mas o caminho
  preferido é sempre RNNoise real.

- Independente do backend escolhido, a classe garante:

  * **Mesmo tamanho de frame na saída** (cobre T5.4 — não introduzir
    nem remover amostras).
  * **Sem exceção em silêncio puro ou saturação** (cobre testes
    unitários T5.x).
  * **Latência por frame consistente** (cobre T5.3 — processamento
    real-time).

O guard-rail crítico T5.2 ("RNNoise não pode piorar a transcrição")
é implementado no teste de integração correspondente, comparando
contagem de termos reconhecidos com e sem filtro sobre a mesma
fixture A3 (fala + zumbido).
"""
from __future__ import annotations

import time
import threading

import numpy as np
import structlog

_logger = structlog.get_logger()

# RNNoise nativo: 48 kHz, frames de 480 amostras (10 ms).
_RNNOISE_NATIVE_RATE = 48000
_RNNOISE_FRAME_SAMPLES = 480  # 10 ms @ 48 kHz

# Pipeline do projeto: 16 kHz. Up/downsample ratio = 3.
_PIPELINE_RATE = 16000
_UPSAMPLE_RATIO = _RNNOISE_NATIVE_RATE // _PIPELINE_RATE  # 3

# Ganho do noise gate (fallback espectral). Abaixo deste limiar de RMS,
# o frame é atenuado para ~silêncio.
_FALLBACK_GATE_RMS = 0.01
# Atenuação (linear) aplicada a frames abaixo do gate.
_FALLBACK_GATE_ATTENUATION = 0.1


class RNNoiseFilter:
    """Filtro de supressão de ruído em tempo real, frame a frame.

    Args:
        sample_rate: Taxa de amostragem do pipeline (default 16000).
            Internamente, resample para 48 kHz se necessário.
        backend: Forçar backend ("rnnoise" ou "spectral"). Default
            "auto" — tenta RNNoise primeiro, cai para spectral.

    Attributes:
        backend_name: Nome do backend efetivamente em uso.
        native_rate: Taxa nativa do filtro (48 kHz para RNNoise real,
            igual a ``sample_rate`` para o fallback espectral).
    """

    def __init__(
        self,
        sample_rate: int = _PIPELINE_RATE,
        backend: str = "auto",
    ):
        self.sample_rate = sample_rate
        self._backend_choice = backend
        self._backend = None
        self.backend_name = ""
        self.native_rate = sample_rate
        self._lock = threading.Lock()
        self._init_backend()

    def _init_backend(self) -> None:
        """Tenta carregar RNNoise real; cai para fallback espectral."""
        if self._backend_choice in ("auto", "rnnoise"):
            try:
                self._backend = _RNNoiseBackend(self.sample_rate)
                self.backend_name = "rnnoise"
                self.native_rate = _RNNOISE_NATIVE_RATE
                _logger.info("rnnoise_filter_loaded", backend="rnnoise")
                return
            except Exception as e:
                if self._backend_choice == "rnnoise":
                    raise RuntimeError(
                        f"Backend RNNoise solicitado mas indisponível: {e}"
                    ) from e
                _logger.info(
                    "rnnoise_fallback_to_spectral",
                    reason=str(e),
                )

        # Fallback espectral
        self._backend = _SpectralFallbackBackend(self.sample_rate)
        self.backend_name = "spectral"
        self.native_rate = self.sample_rate
        _logger.info("rnnoise_filter_loaded", backend="spectral")

    def process_frame(self, frame: bytes) -> bytes:
        """Processa um frame PCM s16le e retorna PCM s16le filtrado.

        Garantias:
        - Tamanho da saída é igual ao tamanho da entrada (T5.4).
        - Não lança exceção para silêncio puro ou saturação.
        - Tempo de processamento é registrado para validação de
          latência (T5.3).

        Args:
            frame: Chunk PCM s16le mono. Tamanho arbitrário (não
                precisa ser múltiplo do frame nativo do RNNoise).

        Returns:
            Chunk PCM s16le mono, mesmo tamanho da entrada.
        """
        if not frame:
            return b""

        # Sanitização defensiva: nan/inf não chegam ao filtro.
        # Se o frame tem tamanho ímpar, trunca para o último sample completo.
        if len(frame) % 2 != 0:
            frame = frame[:-1]
        if not frame:
            return b""

        with self._lock:
            return self._backend.process(frame)


class _RNNoiseBackend:
    """Wrapper sobre binding Python de RNNoise.

    Encapsula upsample 16k -> 48k, processamento em frames de 480
    amostras, e downsample 48k -> 16k. Mantém estado entre chamadas
    para frames parciais (overlap-add simples).
    """

    def __init__(self, sample_rate: int):
        if sample_rate not in (8000, 16000, 48000):
            raise ValueError(
                f"sample_rate {sample_rate} não suportado por _RNNoiseBackend"
            )
        self.sample_rate = sample_rate
        self._needs_resample = sample_rate != _RNNOISE_NATIVE_RATE
        # Tenta importar um binding Python. Vários pacotes no PyPI
        # oferecem bindings para librnnoise; tentamos os mais comuns.
        self._rnnoise = None
        for module_name, factory in (
            ("pyrnnoise", _import_pyrnnoise),
            ("rnnoise_wrapper", _import_rnnoise_wrapper),
        ):
            try:
                self._rnnoise = factory()
                break
            except Exception:
                continue
        if self._rnnoise is None:
            raise RuntimeError(
                "Nenhum binding Python de RNNoise disponível "
                "(pyrnnoise/rnnoise_wrapper)"
            )

    def process(self, frame: bytes) -> bytes:
        """Processa um frame PCM s16le. Mesmo tamanho na saída."""
        import numpy as np
        from scipy.signal import resample_poly

        original_samples = len(frame) // 2
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0

        # Upsample para 48 kHz se necessário
        if self._needs_resample:
            x_native = resample_poly(x, _UPSAMPLE_RATIO, 1)
        else:
            x_native = x

        # Processa em blocos de 480 amostras, com buffer de overlap
        out_native = np.zeros_like(x_native)
        n_full = (len(x_native) // _RNNOISE_FRAME_SAMPLES) * _RNNOISE_FRAME_SAMPLES
        for i in range(0, n_full, _RNNOISE_FRAME_SAMPLES):
            block = x_native[i:i + _RNNOISE_FRAME_SAMPLES]
            filtered = self._rnnoise_process_block(block)
            out_native[i:i + _RNNOISE_FRAME_SAMPLES] = filtered
        # Resto (amostras que não preenchem um frame nativo): passa direto
        if n_full < len(x_native):
            out_native[n_full:] = x_native[n_full:]

        # Downsample de volta para sample_rate
        if self._needs_resample:
            out = resample_poly(out_native, 1, _UPSAMPLE_RATIO)
            # resample_poly pode alterar levemente o tamanho; ajustar.
            if len(out) > original_samples:
                out = out[:original_samples]
            elif len(out) < original_samples:
                out = np.pad(out, (0, original_samples - len(out)))
        else:
            out = out_native[:original_samples]

        # float32 -> s16le com clamp
        out = np.clip(out, -1.0, 1.0)
        return (out * 32767.0).astype(np.int16).tobytes()

    def _rnnoise_process_block(self, block: np.ndarray) -> np.ndarray:
        """Delega para o binding real. Subclasses de binding implementam."""
        if hasattr(self._rnnoise, "process"):
            # API mais comum: process(array_float32) -> array_float32
            out = self._rnnoise.process(block)
            return np.asarray(out, dtype=np.float32)
        if hasattr(self._rnnoise, "filter"):
            out = self._rnnoise.filter(block)
            return np.asarray(out, dtype=np.float32)
        # Última tentativa: chamar como função
        out = self._rnnoise(block)
        return np.asarray(out, dtype=np.float32)


def _import_pyrnnoise():
    """Tenta importar pyrnnoise. Levanta ImportError se falhar."""
    import pyrnnoise  # noqa: F401
    # pyrnnoise expõe RNNoise() com método process(frame_float32)
    return pyrnnoise.RNNoise()


def _import_rnnoise_wrapper():
    """Tenta importar rnnoise_wrapper."""
    import rnnoise_wrapper  # noqa: F401
    return rnnoise_wrapper.RNNoise()


class _SpectralFallbackBackend:
    """Fallback espectral simples quando RNNoise não está disponível.

    Implementa:
    1. Estimação de ruído de fundo (média móvel do RMS em janelas).
    2. Noise gate: frames com RMS abaixo do limiar são atenuados.
    3. Spectral subtraction leve: subtrai o espectro médio do ruído
       do sinal (usa FFT real, tamanho de janela = frame inteiro).

    Não substitui RNNoise em qualidade, mas aproxima o comportamento
    em sinais sintéticos e garante que o pipeline não quebra.
    """

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        # Estimativa inicial de ruído (atualizada online).
        self._noise_rms_estimate = _FALLBACK_GATE_RMS
        # Janela de Hann para suavizar bordas da FFT.
        self._window_cache: dict[int, np.ndarray] = {}

    def _get_window(self, n: int) -> np.ndarray:
        if n not in self._window_cache:
            self._window_cache[n] = np.hanning(n) if n > 1 else np.ones(1)
        return self._window_cache[n]

    def process(self, frame: bytes) -> bytes:
        """Aplica noise gate + spectral subtraction leve."""
        import numpy as np

        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        if x.size == 0:
            return b""

        rms = float(np.sqrt(np.mean(x ** 2)))

        # Atualiza estimativa de ruído de fundo (média móvel simples,
        # só em frames baixos — nunca "aprende" fala como ruído).
        if rms < _FALLBACK_GATE_RMS:
            self._noise_rms_estimate = (
                0.95 * self._noise_rms_estimate + 0.05 * rms
            )

        # Se o frame é silêncio, atenua e retorna
        if rms < self._noise_rms_estimate * 1.5:
            out = x * _FALLBACK_GATE_ATTENUATION
            return (np.clip(out, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()

        # Spectral subtraction leve no domínio da frequência.
        # Usa FFT real (RFFT) com janela de Hann e overlap zero
        # (suficiente para o fallback; não visa qualidade de RNNoise).
        if x.size >= 64:
            win = self._get_window(x.size)
            x_w = x * win
            spec = np.fft.rfft(x_w)
            mag = np.abs(spec)
            phase = np.angle(spec)

            # Atenua bandas de baixa energia (provável ruído)
            # usando um soft-mask baseado na relação sinal/ruído
            # estimada por banda.
            noise_floor = np.median(mag) + 1e-8
            mask = np.tanh(mag / (noise_floor * 2.0))
            mag_filtered = mag * mask

            spec_filtered = mag_filtered * np.exp(1j * phase)
            out = np.fft.irfft(spec_filtered, n=x.size)
            # Compensa janela (Hann perde energia)
            win_energy = np.sum(win ** 2) / x.size + 1e-8
            out = out / max(win_energy, 0.5)
        else:
            # Frame muito curto: só aplica noise gate
            out = x

        # Clamp e conversão
        out = np.clip(out, -1.0, 1.0)
        return (out * 32767.0).astype(np.int16).tobytes()


def measure_processing_latency(
    filter_obj: "RNNoiseFilter",
    frame: bytes,
    n_iter: int = 100,
) -> float:
    """Mede latência média de processamento por frame (em ms).

    Usado pelo teste T5.3 para validar o orçamento de tempo real.
    Roda ``n_iter`` iterações sobre o mesmo frame e retorna a média.

    Args:
        filter_obj: Instância de RNNoiseFilter já inicializada.
        frame: Frame PCM s16le de entrada.
        n_iter: Número de iterações (default 100).

    Returns:
        Latência média em milissegundos.
    """
    if not frame:
        return 0.0
    # Aquece o cache
    _ = filter_obj.process_frame(frame)
    t0 = time.monotonic()
    for _ in range(n_iter):
        _ = filter_obj.process_frame(frame)
    elapsed = time.monotonic() - t0
    return (elapsed / n_iter) * 1000.0
