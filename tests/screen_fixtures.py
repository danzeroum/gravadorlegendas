"""Tela de formulário e vídeo sintéticos (só para testes; nenhum dado real)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 800, 450
FACE_BAND = 200   # faixa à direita simulando rostos dos participantes


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:  # pragma: no cover
        return ImageFont.load_default()


def draw_form(question: str, options: list[tuple[str, bool]], *,
              dark: bool = False) -> Image.Image:
    """Tela com uma pergunta e opções com caixa (marcada ou não) + faixa de 'rostos'."""
    bg, fg = ((30, 30, 30), (235, 235, 235)) if dark else ((255, 255, 255), (20, 20, 20))
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    f, fq = _font(22), _font(24)
    d.text((30, 30), question, font=fq, fill=fg)
    y = 100
    for text, marked in options:
        box = (40, y + 2, 64, y + 26)
        if marked:
            d.rectangle(box, fill=(20, 60, 160), outline=(20, 60, 160))
            d.line([(45, y + 14), (51, y + 21), (60, y + 7)], fill=(255, 255, 255), width=3)
        else:
            d.rectangle(box, outline=(130, 130, 130), width=2)
        d.text((80, y), text, font=f, fill=fg)
        y += 50
    d.rectangle((W - FACE_BAND, 0, W, H), fill=(120, 90, 70))   # "rostos"
    return img


def write_video(path: Path, scenes: list[tuple[Image.Image, float]], *,
                fps: int = 5, blur_scenes: set[int] | None = None) -> Path:
    """Escreve mp4 (mpeg4) concatenando ``(imagem, segundos)``.

    ``blur_scenes``: índices de cenas desenhadas borradas (simula rolagem).
    """
    import av

    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=fps)
    stream.width, stream.height, stream.pix_fmt = W, H, "yuv420p"
    stream.options = {"qscale": "2", "g": str(fps)}
    for idx, (img, seconds) in enumerate(scenes):
        if blur_scenes and idx in blur_scenes:
            img = img.filter(ImageFilter.GaussianBlur(6))
        arr = np.asarray(img.convert("RGB"))
        for _ in range(int(seconds * fps)):
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()
    return path
