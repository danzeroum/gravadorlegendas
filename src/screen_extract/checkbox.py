"""Detecção de caixa de seleção marcada à esquerda de uma linha de texto.

Heurística em numpy (sem OpenCV): procura, numa janela à esquerda da linha,
um traço aproximadamente quadrado/redondo e mede quanto do interior está
preenchido. Marcado = preenchido (caixa cheia, ✓ ou ponto do radio).
É uma heurística: confira por amostragem no seu layout do OneTrust.
"""
from __future__ import annotations

import numpy as np

INK_LEVEL = 200      # abaixo disso há "tinta" (borda cinza-clara incluída)
FILL_LEVEL = 120     # abaixo disso conta como preenchimento forte
FILL_MIN = 0.20      # fração do interior preenchida para considerar marcado
WINDOW_H_FACTOR = 3.0


def detect_checkbox(gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool | None:
    """``True``/``False`` se há caixa à esquerda da linha ``(x, y, w, h)``; senão None.

    Args:
        gray: Frame em tons de cinza (uint8), texto escuro em fundo claro.
    """
    if h < 6:
        return None
    pad = max(1, int(0.3 * h))
    top, bottom = max(0, y - pad), min(gray.shape[0], y + h + pad)
    right = max(0, x - 1)
    left = max(0, int(x - WINDOW_H_FACTOR * h))
    if right - left < 0.4 * h or bottom - top < 0.4 * h:
        return None

    win = gray[top:bottom, left:right]
    ink = win < INK_LEVEL
    rows, cols = np.where(ink)
    if rows.size == 0:
        return None
    # Caixa de tinta mais próxima do texto: usa só as colunas do último bloco
    # contíguo (descarta indentação/ícones mais à esquerda).
    col_has = np.zeros(win.shape[1], dtype=bool)
    col_has[np.unique(cols)] = True
    end = int(np.max(np.where(col_has)))
    start = end
    gap = 0
    for c in range(end, -1, -1):
        if col_has[c]:
            start, gap = c, 0
        else:
            gap += 1
            if gap > max(2, int(0.15 * h)):
                break
    block = ink[:, start:end + 1]
    r_idx = np.where(block.any(axis=1))[0]
    bh, bw = int(r_idx.max() - r_idx.min() + 1), end - start + 1
    if not (0.5 * h <= bh <= 1.7 * h and 0.5 * h <= bw <= 1.7 * h):
        return None
    if not 0.7 <= bw / bh <= 1.4:
        return None

    y0, x0 = int(r_idx.min()), start
    inset_y, inset_x = max(1, int(0.25 * bh)), max(1, int(0.25 * bw))
    inner = win[y0 + inset_y:y0 + bh - inset_y, x0 + inset_x:x0 + bw - inset_x]
    if inner.size == 0:
        return None
    return bool((inner < FILL_LEVEL).mean() >= FILL_MIN)
