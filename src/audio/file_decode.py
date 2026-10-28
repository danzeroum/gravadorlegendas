"""Decodificação de arquivos de áudio/vídeo para WAV PCM 16 kHz mono.

Usado pela importação de arquivos (Frente J) e pelo corpus real (Frente H1)
do plano de diarização (``docs/diarizacao/PLANO-IMPLEMENTACAO.md``).

Decodifica com **PyAV** (``av``), que já é dependência do faster-whisper —
não exige ``ffmpeg`` instalado no sistema. Aceita qualquer contêiner que o
FFmpeg embutido no PyAV entenda (mp3, m4a/aac, mp4/mov, ogg/opus, flac,
webm, wav...). De vídeo, usa só a primeira faixa de áudio.

A saída é sempre PCM s16le mono 16 kHz (regra R1 do plano): o mesmo WAV
alimenta Whisper e diarizador, para os tempos baterem.
"""
from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

TARGET_RATE = 16000

# Extensões oferecidas na UI/CLI. A decodificação não depende delas (o
# PyAV detecta pelo conteúdo); servem de filtro de seleção.
SUPPORTED_EXTENSIONS = (
    ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".flac", ".webm",
)


class AudioDecodeError(ValueError):
    """Arquivo ilegível, sem faixa de áudio ou PyAV ausente."""


def decode_to_wav16k(src: str | Path, dest: str | Path | None = None) -> Path:
    """Decodifica ``src`` para WAV PCM s16le mono 16 kHz.

    Args:
        src: Arquivo de áudio ou vídeo.
        dest: Caminho do WAV de saída. Se None, cria um temporário
            (o chamador é responsável por apagá-lo).

    Returns:
        Caminho do WAV gerado.

    Raises:
        AudioDecodeError: PyAV ausente, arquivo inexistente/corrompido ou
            sem faixa de áudio. A mensagem diz o que fazer.
    """
    try:
        import av
        from av.audio.resampler import AudioResampler
    except ImportError as e:
        raise AudioDecodeError(
            "PyAV não instalado — instale as dependências de áudio: "
            "pip install -e \".[audio]\""
        ) from e

    src = Path(src)
    if not src.is_file():
        raise AudioDecodeError(f"Arquivo não encontrado: {src}")

    if dest is None:
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="gravador_import_")
        os.close(fd)
        dest = Path(tmp)
    dest = Path(dest)

    try:
        container = av.open(str(src))
    except Exception as e:  # av.error.FFmpegError e afins
        dest.unlink(missing_ok=True)
        raise AudioDecodeError(
            f"Não foi possível abrir '{src.name}' como áudio/vídeo: {e}"
        ) from e

    try:
        with container:
            if not container.streams.audio:
                raise AudioDecodeError(f"'{src.name}' não tem faixa de áudio.")
            stream = container.streams.audio[0]
            resampler = AudioResampler(
                format="s16", layout="mono", rate=TARGET_RATE,
            )
            samples = 0
            with wave.open(str(dest), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(TARGET_RATE)
                for frame in container.decode(stream):
                    for out in resampler.resample(frame):
                        data = out.to_ndarray().tobytes()
                        samples += len(data) // 2
                        wf.writeframes(data)
                for out in resampler.resample(None):  # flush
                    data = out.to_ndarray().tobytes()
                    samples += len(data) // 2
                    wf.writeframes(data)
    except AudioDecodeError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise AudioDecodeError(
            f"Falha ao decodificar '{src.name}': {e}"
        ) from e

    if samples == 0:
        dest.unlink(missing_ok=True)
        raise AudioDecodeError(f"'{src.name}' não contém áudio decodificável.")
    return dest


def wav_duration_s(path: str | Path) -> float:
    """Duração de um WAV PCM em segundos."""
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())
