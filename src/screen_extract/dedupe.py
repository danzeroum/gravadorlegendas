"""Descarte de frames repetidos (mudança de pixels) e borrados (nitidez).

Em vez de um hash perceptual global (que ignora um "x" marcado numa tela
inteira), compara miniaturas em cinza e mede a fração de pixels que mudou
bastante: pega marcação de caixa, pergunta nova e rolagem, mas ignora o
ruído de compressão do vídeo.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

SIGNATURE_WIDTH = 320
PIXEL_DELTA = 40     # diferença de cinza (0..255) para o pixel contar como mudado


def signature(img: Image.Image) -> np.ndarray:
    """Miniatura em cinza (int16) usada para comparar frames."""
    w = SIGNATURE_WIDTH
    h = max(1, round(img.height * w / img.width))
    return np.asarray(img.convert("L").resize((w, h), Image.BOX), dtype=np.int16)


def changed_fraction(a: np.ndarray, b: np.ndarray) -> float:
    """Fração (0..1) de pixels que mudaram mais que ``PIXEL_DELTA``."""
    if a.shape != b.shape:
        return 1.0
    return float(np.count_nonzero(np.abs(a - b) > PIXEL_DELTA)) / a.size


def sharpness(img: Image.Image) -> float:
    """Variância do laplaciano: cai muito em quadros borrados (rolagem)."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def is_blurry(value: float, reference: float, ratio: float) -> bool:
    """Borrado = nitidez abaixo de ``ratio`` da mediana dos frames mantidos."""
    return reference > 0 and value < ratio * reference
