"""Buffer circular thread-safe para áudio.

Armazena chunks de áudio em memória com capacidade máxima
configurável. Thread-safe para produtor/consumidor.
"""
import threading


class CircularAudioBuffer:
    """Buffer circular thread-safe para chunks de áudio.

    Attributes:
        max_chunks: Número máximo de chunks armazenados.
        sample_rate: Taxa de amostragem (para cálculos de duração).
    """

    def __init__(self, max_chunks: int = 200, sample_rate: int = 16000):
        self.max_chunks = max_chunks
        self.sample_rate = sample_rate
        self._buffer: list[bytes] = []
        self._lock = threading.Lock()

    def push(self, chunk: bytes):
        """Adiciona um chunk ao buffer (thread-safe)."""
        with self._lock:
            self._buffer.append(chunk)
            if len(self._buffer) > self.max_chunks:
                self._buffer.pop(0)

    def pop_all(self) -> list[bytes]:
        """Remove e retorna todos os chunks atuais."""
        with self._lock:
            data = list(self._buffer)
            self._buffer.clear()
            return data

    def peek(self) -> list[bytes]:
        """Retorna cópia dos chunks sem remover."""
        with self._lock:
            return list(self._buffer)

    @property
    def duration_ms(self) -> float:
        """Duração aproximada do áudio no buffer em ms."""
        with self._lock:
            total_samples = sum(len(c) for c in self._buffer)
            return (total_samples / self.sample_rate) * 1000

    def clear(self):
        """Limpa o buffer."""
        with self._lock:
            self._buffer.clear()
