"""Frente D ao vivo: segmentos do Whisper viram .txt/.srt/.vtt ao parar.

Cobre o bug em que a gravação de áudio nunca gerava legendas porque os
segmentos emitidos pelo ``TranscriberProcess`` eram descartados.
"""
import queue
import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from src.audio import manager as manager_mod
from src.audio.manager import AudioManager
from src.audio.transcribe import TranscriberProcess
from src.config import settings

SR_BYTES = 16000 * 2


# ---------------------------------------------------------------------------
# TranscriberProcess.run() com modelo falso (sem faster-whisper)
# ---------------------------------------------------------------------------

class _FakeWhisper:
    def __init__(self, *a, **k):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        dur = len(audio) / 16000.0
        self.calls.append(dur)
        n = len(self.calls)
        # Fim estimado além do batch (+0.3 s), como o Whisper às vezes faz.
        return iter([
            SimpleNamespace(start=0.5, end=dur - 0.5, text=f" fala {n} "),
            SimpleNamespace(start=dur - 0.4, end=dur + 0.3, text="cauda"),
        ]), None


class _StopAfterEmpty(queue.Queue):
    """Fila que sinaliza parada quando esvazia (simula o usuário parando)."""

    def __init__(self, proc):
        super().__init__()
        self._proc = proc

    def get(self, block=True, timeout=None):
        try:
            return super().get(block=False)
        except queue.Empty:
            self._proc.stop()
            raise


def _run_transcriber(monkeypatch, pcm: bytes, chunk_duration=2.0):
    fake_mod = types.ModuleType("faster_whisper")
    model = _FakeWhisper()
    fake_mod.WhisperModel = lambda *a, **k: model
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)

    out = queue.Queue()
    proc = TranscriberProcess(None, out, chunk_duration=chunk_duration)
    inp = _StopAfterEmpty(proc)
    for i in range(0, len(pcm), 960):
        inp.put(pcm[i:i + 960])
    proc._input = inp
    proc.run()
    results = []
    while not out.empty():
        results.append(out.get_nowait())
    return model, results


def test_transcriber_offsets_by_audio_position_and_flushes_tail(monkeypatch):
    # 5 s de áudio com batches de 2 s: 2 batches cheios + resto de 1 s.
    pcm = (np.ones(16000 * 5, dtype=np.int16) * 1000).tobytes()
    model, results = _run_transcriber(monkeypatch, pcm)

    assert model.calls == [2.0, 2.0, 1.0]
    assert results[-1] == {"done": True}
    segs = [s for r in results if "segments" in r for s in r["segments"]]
    # Offset = posição do batch no áudio (0 s, 2 s, 4 s), não o relógio.
    # Fim limitado ao fim do batch (sem sobreposição com o próximo);
    # no resto de 1 s, "fala 3" (0.5→0.5) tem duração zero e é descartada.
    assert [(s["start"], s["end"], s["text"]) for s in segs] == [
        (0.5, 1.5, "fala 1"), (1.6, 2.0, "cauda"),
        (2.5, 3.5, "fala 2"), (3.6, 4.0, "cauda"),
        (4.6, 5.0, "cauda"),
    ]


def test_transcriber_ignores_tiny_tail(monkeypatch):
    pcm = (np.ones(int(16000 * 2.2), dtype=np.int16) * 1000).tobytes()
    model, results = _run_transcriber(monkeypatch, pcm)
    assert model.calls == [2.0]  # 0.2 s de resto < mínimo de flush
    assert results[-1] == {"done": True}


# ---------------------------------------------------------------------------
# AudioManager: acumula segmentos, drena ao parar e exporta
# ---------------------------------------------------------------------------

class _FakeTranscriber:
    def __init__(self, mgr, pending):
        self._mgr = mgr
        self._pending = pending
        self.stopped = False

    def stop(self):
        self.stopped = True
        for item in self._pending:
            self._mgr._transcript_queue.put(item)

    def is_alive(self):
        return False


def _manager_with_session(tmp_path, monkeypatch, prefix="reuniao"):
    monkeypatch.setattr(settings, "recording_dir", str(tmp_path))
    monkeypatch.setattr(settings, "export_srt", True)
    monkeypatch.setattr(settings, "export_vtt", True)
    mgr = AudioManager()
    mgr._transcript_queue = queue.Queue()
    mgr.capture = SimpleNamespace(stop=lambda: None)
    mgr._subtitle_base = str(tmp_path / f"{prefix}_2026-01-01_10-00-00")
    mgr._is_running = True
    return mgr


def test_stop_drains_last_batch_and_writes_subtitles(tmp_path, monkeypatch):
    mgr = _manager_with_session(tmp_path, monkeypatch)
    received = []
    mgr.on_transcription = lambda text, speaker: received.append(text)

    # Batch já recebido durante a sessão.
    mgr._handle_transcript({
        "text": "Bom dia a todos.", "start": 0.0, "end": 7.0, "batch": 1,
        "segments": [{"start": 0.4, "end": 2.1, "text": "Bom dia a todos."}],
    })
    # Último batch só chega depois do stop (flush do transcriber).
    mgr._transcriber = _FakeTranscriber(mgr, [
        {"text": "Até a próxima.", "start": 7.0, "end": 9.0, "batch": 2,
         "segments": [{"start": 7.2, "end": 8.9, "text": "Até a próxima."}]},
        {"done": True},
    ])

    mgr.stop()

    assert received == ["Bom dia a todos.", "Até a próxima."]
    base = tmp_path / "reuniao_2026-01-01_10-00-00"
    assert mgr.subtitle_paths == [
        str(base) + ".txt", str(base) + ".srt", str(base) + ".vtt",
    ]
    srt = (tmp_path / "reuniao_2026-01-01_10-00-00.srt").read_text(encoding="utf-8")
    assert "00:00:00,400 --> 00:00:02,100\nBom dia a todos." in srt
    assert "00:00:07,200 --> 00:00:08,900\nAté a próxima." in srt
    vtt = (tmp_path / "reuniao_2026-01-01_10-00-00.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    txt = (tmp_path / "reuniao_2026-01-01_10-00-00.txt").read_text(encoding="utf-8")
    assert txt == "[00:00:00] Bom dia a todos.\n[00:00:07] Até a próxima.\n"


def test_stop_without_speech_creates_no_files(tmp_path, monkeypatch):
    mgr = _manager_with_session(tmp_path, monkeypatch)
    mgr._transcriber = _FakeTranscriber(mgr, [{"done": True}])
    mgr.stop()
    assert mgr.subtitle_paths == []
    assert list(tmp_path.iterdir()) == []


def test_export_respects_srt_vtt_flags(tmp_path, monkeypatch):
    mgr = _manager_with_session(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "export_vtt", False)
    mgr._handle_transcript({
        "text": "Olá", "segments": [{"start": 0.0, "end": 1.0, "text": "Olá"}],
    })
    mgr._transcriber = _FakeTranscriber(mgr, [{"done": True}])
    mgr.stop()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "reuniao_2026-01-01_10-00-00.srt", "reuniao_2026-01-01_10-00-00.txt",
    ]


def test_drain_times_out_if_transcriber_hangs(tmp_path, monkeypatch):
    mgr = _manager_with_session(tmp_path, monkeypatch)
    monkeypatch.setattr(manager_mod, "_TRANSCRIBER_FLUSH_TIMEOUT_S", 0.3)
    hung = _FakeTranscriber(mgr, [])
    hung.is_alive = lambda: True
    mgr._transcriber = hung
    mgr.stop()  # não deve travar
    assert mgr.subtitle_paths == []


@pytest.mark.parametrize("prefix,expected", [("reuniao", "reuniao_"), ("  ", "legendas_")])
def test_start_builds_subtitle_base_from_prefix(tmp_path, monkeypatch, prefix, expected):
    monkeypatch.setattr(settings, "recording_dir", str(tmp_path))
    mgr = AudioManager()
    started = []
    monkeypatch.setattr(manager_mod, "TranscriberProcess",
                        lambda *a, **k: SimpleNamespace(start=lambda: started.append(1)))
    mgr.capture = SimpleNamespace(start=lambda q: None, stop=lambda: None,
                                  device_index=None)
    mgr.start(enable_diarization=False, record_raw=False,
              noise_suppression=False, output_prefix=prefix)
    try:
        assert mgr._subtitle_base.startswith(str(tmp_path / expected))
        assert started == [1]
    finally:
        mgr._is_running = False
