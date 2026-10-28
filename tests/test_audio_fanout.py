"""FILA-01..02 — fan-out do AudioManager (Frente E1, D-017).

Antes da correção, Whisper e diarizador liam da MESMA
``multiprocessing.Queue``: cada chunk ia para só um deles.
"""
import queue

from src.audio.manager import AudioManager


class _StopWhenEmpty(queue.Queue):
    """Fila master que encerra o loop quando esvazia."""

    def __init__(self, manager):
        super().__init__()
        self._manager = manager

    def get(self, block=True, timeout=None):
        try:
            return super().get(block=False)
        except queue.Empty:
            self._manager._is_running = False
            raise


class _InvertFilter:
    """Filtro falso: troca cada byte, para distinguir saída filtrada."""

    def process_frame(self, frame: bytes) -> bytes:
        return bytes(255 - b for b in frame)


def _run_fanout(chunks, *, diarizer=True, noise_filter=None):
    am = AudioManager()
    am._master_queue = _StopWhenEmpty(am)
    am._audio_queue = queue.Queue()
    am._diarization_audio_queue = queue.Queue()
    am._diarizer = object() if diarizer else None
    am._noise_filter = noise_filter
    for c in chunks:
        am._master_queue.put(c)
    am._is_running = True
    am._fanout_loop()
    return am


def _drain(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


CHUNKS = [bytes([i]) * 960 for i in range(1, 21)]


def test_whisper_and_diarizer_receive_every_chunk_in_order():
    am = _run_fanout(CHUNKS)
    assert _drain(am._audio_queue) == CHUNKS
    assert _drain(am._diarization_audio_queue) == CHUNKS


def test_queues_are_distinct_objects():
    am = AudioManager()
    assert am._audio_queue is not am._diarization_audio_queue


def test_diarizer_gets_unfiltered_audio_when_noise_suppression_on():
    am = _run_fanout(CHUNKS, noise_filter=_InvertFilter())
    whisper = _drain(am._audio_queue)
    diar = _drain(am._diarization_audio_queue)
    assert diar == CHUNKS
    assert whisper == [_InvertFilter().process_frame(c) for c in CHUNKS]
    # WAV de reprocessamento (diarização offline) também sem filtro.
    assert am._recorded_chunks == CHUNKS


def test_no_diarizer_means_no_diarization_feed():
    am = _run_fanout(CHUNKS, diarizer=False)
    assert _drain(am._audio_queue) == CHUNKS
    assert am._diarization_audio_queue.empty()
