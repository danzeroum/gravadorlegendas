"""Pipeline: frames → recorte → dedupe → leitura → consolidação."""
from __future__ import annotations

import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from src.screen_extract.consolidate import consolidate
from src.screen_extract.crop import Region, crop
from src.screen_extract.dedupe import changed_fraction, is_blurry, sharpness, signature
from src.screen_extract.frames import iter_frames
from src.screen_extract.models import Item, Leitura
from src.screen_extract.reader import FrameReader

ProgressCallback = Callable[[float, str], None]


@dataclass
class Extraction:
    duration_s: float | None
    sampled: int = 0
    kept: int = 0
    blurry: int = 0
    leituras: list[Leitura] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)


def extract(video: str | Path, region: Region, reader: FrameReader, *,
            interval_s: float = 2.0, change_threshold: float = 0.0005,
            blur_ratio: float = 0.5, on_progress: ProgressCallback | None = None
            ) -> Extraction:
    """Extrai o estado final de cada item mostrado na tela compartilhada.

    Args:
        change_threshold: Fração de pixels (0.0005 = 0,05%) que precisa mudar
            em relação ao último frame mantido para contar como "algo mudou".
        blur_ratio: Frames com nitidez abaixo de ``ratio × mediana`` (rolagem)
            são descartados.

    Os frames mantidos ficam só numa pasta temporária, apagada ao final.
    """
    def progress(f: float, stage: str) -> None:
        if on_progress is not None:
            on_progress(max(0.0, min(1.0, f)), stage)

    result = Extraction(duration_s=None)
    with tempfile.TemporaryDirectory(prefix="screen_extract_") as tmp:
        kept: list[tuple[float, float, Path]] = []   # (t, nitidez, png)
        last_sig = None
        for t, frame, duration in iter_frames(video, interval_s):
            result.duration_s = duration
            result.sampled += 1
            img = crop(frame, region)
            sig = signature(img)
            if last_sig is None or changed_fraction(sig, last_sig) >= change_threshold:
                last_sig = sig
                path = Path(tmp) / f"{len(kept):06d}.png"
                img.save(path)
                kept.append((t, sharpness(img), path))
            if duration:
                progress(0.5 * min(t / duration, 1.0), "Procurando mudanças na tela…")

        ref = statistics.median(s for _, s, _ in kept) if kept else 0.0
        sharp = [k for k in kept if not is_blurry(k[1], ref, blur_ratio)]
        result.blurry = len(kept) - len(sharp)
        result.kept = len(sharp)

        for n, (t, _, path) in enumerate(sharp, 1):
            with Image.open(path) as img:
                result.leituras.append(Leitura(t, reader.read(img)))
            progress(0.5 + 0.5 * n / len(sharp), "Lendo os textos…")

    result.items = consolidate(result.leituras)
    progress(1.0, "Pronto")
    return result
