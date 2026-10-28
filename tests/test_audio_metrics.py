from src.audio.metrics import LatencyTracker, OverlapCounter


class TestLatencyTracker:
    def test_empty_avg(self):
        t = LatencyTracker()
        assert t.avg == 0.0

    def test_empty_p95(self):
        t = LatencyTracker()
        assert t.p95 == 0.0

    def test_single_mark(self):
        t = LatencyTracker()
        t.mark_receive(1)
        assert t.avg == 0.0

    def test_avg_two_marks(self):
        import time
        t = LatencyTracker(max_samples=10)
        t.mark_receive(1)
        time.sleep(0.01)
        t.mark_receive(2)
        assert t.avg > 0

    def test_p95_equal_avg_single_gap(self):
        import time
        t = LatencyTracker(max_samples=10)
        t.mark_receive(1)
        time.sleep(0.01)
        t.mark_receive(2)
        assert t.p95 == t.avg

    def test_max_samples_limits_history(self):
        t = LatencyTracker(max_samples=3)
        for i in range(10):
            t.mark_receive(i)
        assert len(t._history) <= 3

    def test_log_empty_does_not_raise(self):
        t = LatencyTracker()
        t.log("test")


class TestOverlapCounter:
    def test_empty_returns_zero(self):
        c = OverlapCounter()
        assert c.overlap_pct == 0.0

    def test_single_segment_no_overlap(self):
        c = OverlapCounter()
        c.feed_segments([{"speaker": "A", "start": 0, "end": 5}])
        assert c.overlap_pct == 0.0

    def test_two_non_overlapping_segments(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 5},
            {"speaker": "B", "start": 5, "end": 10},
        ])
        assert c.overlap_pct == 0.0

    def test_two_overlapping_segments(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 6},
            {"speaker": "B", "start": 4, "end": 10},
        ])
        assert c.overlap_pct == 20.0

    def test_multiple_overlaps(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 5},
            {"speaker": "B", "start": 3, "end": 8},
            {"speaker": "C", "start": 6, "end": 10},
        ])
        assert c.overlap_pct > 0

    def test_log_empty_does_not_raise(self):
        c = OverlapCounter()
        c.log("test")


class TestOverlapCounterSweep:
    """ALN-06 — sweep line, só falantes distintos (docs/diarizacao, ACH-05)."""

    def test_same_speaker_overlap_is_not_counted(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 6},
            {"speaker": "A", "start": 4, "end": 10},
        ])
        assert c.overlap_pct == 0.0

    def test_exact_value_two_speakers(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 5},
            {"speaker": "B", "start": 3, "end": 8},
            {"speaker": "C", "start": 6, "end": 10},
        ])
        # overlap: 3–5 (A+B) e 6–8 (B+C) = 4 s de 10 s
        assert c.overlap_pct == 40.0

    def test_three_simultaneous_speakers_not_double_counted(self):
        c = OverlapCounter()
        c.feed_segments([
            {"speaker": "A", "start": 0, "end": 10},
            {"speaker": "B", "start": 0, "end": 10},
            {"speaker": "C", "start": 0, "end": 10},
        ])
        assert c.overlap_pct == 100.0

    def test_many_segments_fast(self):
        import time
        c = OverlapCounter()
        c.feed_segments([{"speaker": "AB"[i % 2], "start": i, "end": i + 1.5}
                         for i in range(20_000)])
        t0 = time.perf_counter()
        pct = c.overlap_pct
        assert time.perf_counter() - t0 < 1.0
        assert 40 < pct < 60
