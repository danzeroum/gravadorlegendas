"""Gera arquivos de mídia sintéticos (mp3/m4a/mp4/ogg/flac) com PyAV.

Só para testes: nenhum áudio real (regra R3 de docs/diarizacao).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def write_tone(path: Path, codec: str, *, duration_s: float = 2.0,
               rate: int = 44100, layout: str = "stereo",
               freq: float = 440.0, with_video: bool = False) -> Path:
    """Escreve uma senoide codificada com ``codec`` em ``path``."""
    import av
    from av.audio.resampler import AudioResampler

    container = av.open(str(path), "w")
    video = None
    if with_video:
        video = container.add_stream("mpeg4", rate=25)
        video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
    stream = container.add_stream(codec, rate=rate)
    stream.layout = layout
    resampler = AudioResampler(format=stream.format.name, layout=layout,
                               rate=rate)

    n = int(rate * duration_s)
    t = np.arange(n) / rate
    tone = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    channels = 2 if layout == "stereo" else 1
    step = 1024
    for i in range(0, n, step):
        block = np.tile(tone[i:i + step], (channels, 1))
        frame = av.AudioFrame.from_ndarray(block, format="fltp",
                                           layout=layout)
        frame.sample_rate = rate
        for out in resampler.resample(frame):
            for packet in stream.encode(out):
                container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    if video is not None:
        black = np.zeros((64, 64, 3), np.uint8)
        for _ in range(int(25 * duration_s)):
            frame = av.VideoFrame.from_ndarray(black, format="rgb24")
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
    container.close()
    return path
