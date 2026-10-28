"""Telemetria leve para o pipeline de áudio.

Métricas: latência de transcrição, sobreposição de falantes,
contagem de palavras e taxa de erro (WER) quando referência
estiver disponível.
"""
import time
import structlog

_logger = structlog.get_logger()


class LatencyTracker:
    """Rastreia intervalo entre transcrições consecutivas.

    Attributes:
        history: Lista de latências registradas (segundos).
    """

    def __init__(self, max_samples: int = 100):
        self._last_ts: float | None = None
        self._history: list[float] = []
        self._max_samples = max_samples

    def mark_receive(self, batch: int):
        """Registra chegada de um batch transcrito."""
        now = time.monotonic()
        if self._last_ts is not None:
            gap = now - self._last_ts
            self._history.append(gap)
            if len(self._history) > self._max_samples:
                self._history.pop(0)
        self._last_ts = now

    @property
    def avg(self) -> float:
        """Intervalo médio entre transcrições (segundos)."""
        if not self._history:
            return 0.0
        return sum(self._history) / len(self._history)

    @property
    def p95(self) -> float:
        """Intervalo no percentil 95."""
        if not self._history:
            return 0.0
        sorted_vals = sorted(self._history)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def log(self, stage: str = ""):
        """Envia métricas de latência para o log estruturado."""
        if not self._history:
            return
        _logger.info(
            "latency_metrics",
            stage=stage,
            avg_gap=round(self.avg, 3),
            p95_gap=round(self.p95, 3),
            samples=len(self._history),
        )


class OverlapCounter:
    """Calcula sobreposição entre falantes a partir de segmentos de diarização.

    Attributes:
        total_overlap: Tempo total de sobreposição (segundos).
        total_duration: Duração total analisada (segundos).
    """

    def __init__(self):
        self._segments: list[dict] = []

    def feed_segments(self, segments: list[dict]):
        """Adiciona segmentos para cálculo de overlap."""
        self._segments.extend(segments)

    def _compute(self):
        """Calcula overlap com base nos segmentos acumulados.

        Varredura de eventos (+1 no início, −1 no fim) com contador por
        falante: conta o tempo em que há **dois ou mais falantes
        distintos** ativos. O(n log n). Segmentos do mesmo falante que se
        sobrepõem (comuns na saída incremental do diart) não contam, e três
        falantes simultâneos não contam em dobro.
        """
        segs = [s for s in self._segments if s["end"] > s["start"]]
        if len(segs) < 2:
            return 0.0, 0.0
        duration = max(s["end"] for s in segs) - min(s["start"] for s in segs)
        # Fim antes de início no mesmo instante: encostar não é sobrepor.
        events = sorted(
            [(s["start"], 1, s["speaker"]) for s in segs]
            + [(s["end"], -1, s["speaker"]) for s in segs],
            key=lambda e: (e[0], e[1]),
        )
        active: dict = {}
        overlap = 0.0
        prev_t = events[0][0]
        for t, delta, speaker in events:
            if len(active) >= 2:
                overlap += t - prev_t
            prev_t = t
            count = active.get(speaker, 0) + delta
            if count > 0:
                active[speaker] = count
            else:
                active.pop(speaker, None)
        return overlap, duration

    @property
    def overlap_pct(self) -> float:
        """Percentual de tempo com sobreposição de falas."""
        overlap, duration = self._compute()
        if duration <= 0:
            return 0.0
        return (overlap / duration) * 100

    def log(self, stage: str = ""):
        """Envia métricas de overlap para o log estruturado."""
        overlap, duration = self._compute()
        _logger.info(
            "overlap_metrics",
            stage=stage,
            overlap_pct=round(self.overlap_pct, 1),
            overlap_s=round(overlap, 2),
            duration_s=round(duration, 2),
        )
