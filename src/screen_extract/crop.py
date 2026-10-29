"""Recorte da área da tela compartilhada (tira os rostos da análise)."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


class RegionError(ValueError):
    """Região inválida ou fora do frame."""


@dataclass(frozen=True)
class Region:
    """Retângulo ``x, y, largura, altura`` em pixels ou em frações (0..1)."""

    x: float
    y: float
    w: float
    h: float
    relative: bool = False

    def to_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """Caixa ``(esq, topo, dir, base)`` em pixels, validada contra o frame."""
        if self.relative:
            x, y = round(self.x * width), round(self.y * height)
            w, h = round(self.w * width), round(self.h * height)
        else:
            x, y, w, h = round(self.x), round(self.y), round(self.w), round(self.h)
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
            raise RegionError(
                f"Região {x},{y},{w},{h} não cabe no frame de {width}x{height}. "
                "Use --calibrar para ver o frame e ajustar.")
        return x, y, x + w, y + h


def parse_region(text: str) -> Region:
    """``"100,80,1400,900"`` (pixels) ou ``"5%,8%,70%,85%"`` (percentuais)."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise RegionError("Use x,y,largura,altura (ex.: 100,80,1400,900 ou "
                          "5%,8%,70%,85%).")
    percent = [p.endswith("%") for p in parts]
    if any(percent) and not all(percent):
        raise RegionError("Não misture pixels e percentuais na região.")
    try:
        nums = [float(p.rstrip("%")) for p in parts]
    except ValueError as e:
        raise RegionError(f"Região inválida: '{text}'.") from e
    if all(percent):
        nums = [n / 100 for n in nums]
    return Region(*nums, relative=all(percent))


def crop(img: Image.Image, region: Region) -> Image.Image:
    """Recorta ``img`` pela região (cópia independente do frame original)."""
    return img.crop(region.to_box(*img.size)).copy()
