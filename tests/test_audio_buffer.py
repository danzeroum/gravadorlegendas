from src.audio.buffer import CircularAudioBuffer


class TestCircularAudioBuffer:
    def test_push_and_pop_all(self):
        buf = CircularAudioBuffer(max_chunks=10)
        buf.push(b"\x00\x01")
        buf.push(b"\x02\x03")
        result = buf.pop_all()
        assert result == [b"\x00\x01", b"\x02\x03"]

    def test_pop_all_clears_buffer(self):
        buf = CircularAudioBuffer(max_chunks=10)
        buf.push(b"\x00\x01")
        buf.pop_all()
        assert buf.pop_all() == []

    def test_max_chunks_evicts_oldest(self):
        buf = CircularAudioBuffer(max_chunks=2)
        buf.push(b"\x00")
        buf.push(b"\x01")
        buf.push(b"\x02")
        result = buf.pop_all()
        assert result == [b"\x01", b"\x02"]

    def test_peek_returns_copy(self):
        buf = CircularAudioBuffer(max_chunks=10)
        buf.push(b"\x00")
        peeked = buf.peek()
        assert peeked == [b"\x00"]
        buf.pop_all()
        assert buf.peek() == []

    def test_clear_empties_buffer(self):
        buf = CircularAudioBuffer(max_chunks=10)
        buf.push(b"\x00")
        buf.clear()
        assert buf.pop_all() == []

    def test_duration_ms(self):
        buf = CircularAudioBuffer(sample_rate=16000)
        buf.push(b"\x00" * 16000)
        assert buf.duration_ms == 1000.0

    def test_duration_ms_empty(self):
        buf = CircularAudioBuffer()
        assert buf.duration_ms == 0.0

    def test_thread_safety(self):
        import threading
        buf = CircularAudioBuffer(max_chunks=100)
        errors = []

        def producer():
            for i in range(50):
                buf.push(bytes([i & 0xFF]))

        def consumer():
            for _ in range(10):
                try:
                    buf.pop_all()
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=producer),
            threading.Thread(target=consumer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
