"""Leitura de frames do vídeo com PyAV (já dependência do projeto)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from PIL import Image


class VideoDecodeError(ValueError):
    """Arquivo ilegível, sem faixa de vídeo ou PyAV ausente."""


def iter_frames(path: str | Path, interval_s: float = 2.0
                ) -> Iterator[tuple[float, Image.Image, float | None]]:
    """Gera ``(instante_s, imagem RGB, duração_s)`` a cada ``interval_s``.

    Usa seek até o quadro-chave anterior e decodifica até o instante pedido,
    em vez de decodificar o vídeo inteiro. A duração é None se o contêiner
    não a informa (então lê até acabar os quadros).
    """
    if interval_s <= 0:
        raise ValueError("interval_s deve ser positivo.")
    try:
        import av
    except ImportError as e:  # pragma: no cover
        raise VideoDecodeError("PyAV não instalado (pip install av).") from e

    try:
        container = av.open(str(path))
    except (av.error.FFmpegError, OSError) as e:
        raise VideoDecodeError(f"Não consegui abrir '{path}': {e}") from e

    with container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            raise VideoDecodeError("O arquivo não tem faixa de vídeo "
                                   "(este fluxo precisa de gravação de tela).")
        duration = None
        if container.duration:
            duration = container.duration / av.time_base
        elif stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)

        t = 0.0
        while duration is None or t < duration:
            try:
                frame = _frame_at(container, stream, t)
            except (av.error.FFmpegError, OSError) as e:
                raise VideoDecodeError(f"Erro ao decodificar o vídeo: {e}") from e
            if frame is None:
                break
            yield (frame.time if frame.time is not None else t,
                   frame.to_image().convert("RGB"), duration)
            t += interval_s


def _frame_at(container, stream, t: float):
    """Primeiro quadro com instante >= ``t`` (None se passou do fim)."""
    container.seek(int(t / stream.time_base), stream=stream, backward=True)
    for frame in container.decode(stream):
        if frame.time is None or frame.time >= t - 1e-3:
            return frame
    return None
