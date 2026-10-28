"""IMP-01 — decodificação de mp3/m4a/mp4/ogg/flac para WAV 16 kHz mono."""
import wave

import numpy as np
import pytest

pytest.importorskip("av", reason="PyAV ausente (vem com faster-whisper / extra audio)")

from src.audio.file_decode import (  # noqa: E402
    AudioDecodeError, decode_to_wav16k, wav_duration_s,
)
from tests.media_fixtures import write_tone  # noqa: E402

CASES = [
    ("tom.mp3", "mp3", {}),
    ("tom.m4a", "aac", {}),
    ("video.mp4", "aac", {"with_video": True}),
    ("whatsapp.ogg", "libopus", {"rate": 48000}),
    ("tom.flac", "flac", {"layout": "mono"}),
    ("tom.wav", "pcm_s16le", {"rate": 48000}),
]


@pytest.mark.parametrize("name,codec,kw", CASES, ids=[c[0] for c in CASES])
def test_decodes_to_wav16k_mono(tmp_path, name, codec, kw):
    src = write_tone(tmp_path / name, codec, duration_s=2.0, **kw)
    out = decode_to_wav16k(src, tmp_path / "out.wav")
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
    # Codecs com perda adicionam priming/padding (~1 frame do codec).
    assert wav_duration_s(out) == pytest.approx(2.0, abs=0.06)
    # O tom sobrevive (não é silêncio).
    assert np.abs(pcm.astype(np.float64)).mean() > 1000


def test_temp_file_when_no_dest(tmp_path):
    src = write_tone(tmp_path / "a.mp3", "mp3", duration_s=0.5)
    out = decode_to_wav16k(src)
    try:
        assert out.exists() and out.suffix == ".wav"
    finally:
        out.unlink()


def test_missing_file_is_actionable(tmp_path):
    with pytest.raises(AudioDecodeError, match="não encontrado"):
        decode_to_wav16k(tmp_path / "nao_existe.mp3")


def test_corrupted_file_raises_and_leaves_no_output(tmp_path):
    bad = tmp_path / "corrompido.mp3"
    bad.write_bytes(b"isto nao e audio" * 100)
    dest = tmp_path / "out.wav"
    with pytest.raises(AudioDecodeError):
        decode_to_wav16k(bad, dest)
    assert not dest.exists()
