"""ALN-04 — falante por palavra ao vivo (Frente F, regressão de ACH-03)."""
import queue
import sys
import types
from types import SimpleNamespace

import numpy as np

from src.audio.manager import AudioManager
from src.audio.transcribe import TranscriberProcess


class _WordWhisper:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        words = [SimpleNamespace(start=0.5 + i * 0.5, end=0.9 + i * 0.5, word=f" w{i}")
                 for i in range(4)]
        seg = SimpleNamespace(start=0.5, end=2.4, text=" w0 w1 w2 w3",
                              words=words if kwargs.get("word_timestamps") else None)
        return iter([seg]), None


def _run(monkeypatch, word_timestamps):
    model = _WordWhisper()
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = lambda *a, **k: model
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    out = queue.Queue()
    proc = TranscriberProcess(None, out, chunk_duration=2.0,
                              word_timestamps=word_timestamps)
    pcm = (np.ones(16000 * 4, dtype=np.int16) * 500).tobytes()
    proc._transcribe_batch(model, pcm[:64000], 2, 64000, 4.0)  # 2º batch, offset 2 s
    return model, out.get_nowait()


def test_transcriber_emits_absolute_words_when_enabled(monkeypatch):
    model, result = _run(monkeypatch, True)
    assert model.kwargs["word_timestamps"] is True
    assert result["words"][0] == {"start": 2.5, "end": 2.9, "text": "w0"}
    # A 4ª palavra (2.0–2.4 relativo) começa no fim do lote (4.0 s absoluto)
    # e é cortada pelo mesmo limite aplicado aos segmentos.
    assert [w["text"] for w in result["words"]] == ["w0", "w1", "w2"]


def test_transcriber_has_no_words_key_when_disabled(monkeypatch):
    model, result = _run(monkeypatch, False)
    assert model.kwargs["word_timestamps"] is False
    assert "words" not in result


def test_manager_splits_batch_by_speaker():
    am = AudioManager()
    am._speaker_segments.extend([
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 3.5},
        {"speaker": "SPEAKER_01", "start": 3.5, "end": 7.0},
    ])
    emitted = []
    am.on_transcription = lambda text, speaker: emitted.append((text, speaker))
    am._handle_transcript({
        "text": "bom dia oi tudo", "start": 0.0, "end": 7.0, "batch": 1,
        "segments": [{"start": 0.0, "end": 7.0, "text": "bom dia oi tudo"}],
        "words": [
            {"start": 0.5, "end": 1.0, "text": "bom"},
            {"start": 1.1, "end": 1.5, "text": "dia"},
            {"start": 4.0, "end": 4.4, "text": "oi"},
            {"start": 4.5, "end": 5.0, "text": "tudo"},
        ],
    })
    assert emitted == [("bom dia", "SPEAKER_00"), ("oi tudo", "SPEAKER_01")]
    assert [(s.text, s.speaker) for s in am.caption_segments] == emitted


def test_manager_without_turns_keeps_old_behavior():
    am = AudioManager()
    emitted = []
    am.on_transcription = lambda text, speaker: emitted.append((text, speaker))
    am._handle_transcript({
        "text": "bom dia", "start": 0.0, "end": 2.0, "batch": 1,
        "segments": [{"start": 0.0, "end": 2.0, "text": "bom dia"}],
        "words": [{"start": 0.5, "end": 1.0, "text": "bom"}],
    })
    assert emitted == [("bom dia", None)]
    assert am.caption_segments[0].speaker is None
