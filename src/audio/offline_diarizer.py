"""Diarização offline de arquivo com pyannote.audio (Frente E, D-018).

"Quem falou quando" num WAV inteiro, para reprocessamento ao parar a
gravação e para importação de arquivos. O streaming ao vivo continua no
diart (``src/audio/diarize.py``).

Compatível com pyannote.audio 3.x (``Pipeline`` devolve ``Annotation``,
token em ``use_auth_token``) e 4.x (``DiarizeOutput`` com
``exclusive_speaker_diarization``, token em ``token``). O áudio é passado
em memória (waveform + sample rate) para não depender do decodificador de
arquivos do pyannote.

Rótulos saem normalizados como ``SPEAKER_00``, ``SPEAKER_01``… na ordem da
primeira fala — estáveis entre execuções do mesmo resultado.
"""
from __future__ import annotations

import importlib.util
import os
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog

from src.config import settings

_logger = structlog.get_logger()

# Mesmo diretório usado por scripts/setup_audio_models.py.
DIARIZATION_CACHE = Path.home() / ".cache" / "gravador" / "audio" / "diarization"

MODEL_V3 = "pyannote/speaker-diarization-3.1"
MODEL_V4 = "pyannote/speaker-diarization-community-1"

_TOKEN_ENVS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


@dataclass(frozen=True)
class SpeakerTurn:
    """Turno de fala: ``speaker`` ativo em ``[start, end)`` (segundos)."""

    speaker: str
    start: float
    end: float


class DiarizationUnavailable(RuntimeError):
    """Diarização indisponível: dependência, token ou termos do modelo.

    A mensagem diz o passo a seguir e nunca contém o valor do token.
    """


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------

def make_exclusive(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
    """Uma pessoa por instante.

    Onde há sobreposição, fica quem começou a falar por último (quem "tomou
    a palavra"); ao terminar, o turno anterior retoma se ainda estiver
    ativo. Turnos consecutivos do mesmo falante são unidos.
    """
    valid = [t for t in turns if t.end > t.start]
    if not valid:
        return []
    bounds = sorted({t.start for t in valid} | {t.end for t in valid})
    out: list[SpeakerTurn] = []
    for a, b in zip(bounds, bounds[1:]):
        active = [t for t in valid if t.start <= a and t.end >= b]
        if not active:
            continue
        # Desempate determinístico: início mais tardio, depois turno mais
        # curto (interjeição), depois rótulo.
        winner = max(active, key=lambda t: (t.start, -(t.end - t.start), t.speaker))
        if out and out[-1].speaker == winner.speaker and out[-1].end == a:
            out[-1] = SpeakerTurn(winner.speaker, out[-1].start, b)
        else:
            out.append(SpeakerTurn(winner.speaker, a, b))
    return out


def normalize_labels(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
    """Renomeia para ``SPEAKER_NN`` na ordem da primeira fala."""
    mapping: dict[str, str] = {}
    for t in sorted(turns, key=lambda t: (t.start, t.end)):
        mapping.setdefault(t.speaker, f"SPEAKER_{len(mapping):02d}")
    return sorted(
        (SpeakerTurn(mapping[t.speaker], t.start, t.end) for t in turns),
        key=lambda t: (t.start, t.end, t.speaker),
    )


def _annotation_to_turns(annotation) -> list[SpeakerTurn]:
    return [
        SpeakerTurn(str(label), float(seg.start), float(seg.end))
        for seg, _, label in annotation.itertracks(yield_label=True)
    ]


def _read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """WAV PCM16 → (float32 [canais, amostras], taxa)."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"WAV precisa ser PCM 16-bit: {path}")
        channels, rate = wf.getnchannels(), wf.getframerate()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    audio = pcm.astype(np.float32) / 32768.0
    return audio.reshape(-1, channels).T.copy(), rate


def module_available(name: str) -> bool:
    """``find_spec`` seguro para submódulos.

    ``importlib.util.find_spec("pyannote.audio")`` **lança**
    ``ModuleNotFoundError`` quando o pacote pai (``pyannote``) não existe, em
    vez de devolver None — e a ausência do extra é justamente o caso comum.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def find_hf_token() -> str | None:
    """Token HF do ambiente ou do ``huggingface-cli login`` (nunca logado)."""
    for name in _TOKEN_ENVS:
        if os.environ.get(name):
            return os.environ[name]
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


def default_model() -> str:
    """Modelo padrão conforme a versão instalada do pyannote.audio."""
    try:
        from importlib.metadata import version
        major = int(version("pyannote.audio").split(".")[0])
    except Exception:
        return MODEL_V3
    return MODEL_V4 if major >= 4 else MODEL_V3


# ---------------------------------------------------------------------------
# Diarizador
# ---------------------------------------------------------------------------

class OfflineDiarizer:
    """Diarização de arquivo WAV com ``pyannote.audio``.

    Args:
        model_id: Modelo no Hugging Face. Vazio = ``settings.diarization_model``
            ou, se também vazio, o padrão da versão instalada.
        device: ``"cpu"``, ``"cuda"`` ou ``"auto"``.
        pipeline: Pipeline já carregado (injeção para testes).
    """

    def __init__(self, model_id: str | None = None, device: str | None = None,
                 pipeline=None):
        self.model_id = model_id or settings.diarization_model or default_model()
        self.device = device or settings.diarization_device
        self._pipeline = pipeline

    # -- prontidão ----------------------------------------------------------

    def check_ready(self) -> None:
        """Falha cedo, sem baixar nada, se a diarização não puder rodar."""
        if self._pipeline is not None:
            return
        if not module_available("pyannote.audio"):
            raise DiarizationUnavailable(
                "Separação de falantes indisponível: pyannote.audio não "
                "instalado. Instale com: pip install -e \".[diarization]\""
            )
        if not find_hf_token():
            raise DiarizationUnavailable(
                "Separação de falantes indisponível: token do Hugging Face "
                "ausente. Defina a variável HF_TOKEN (ou rode "
                "'huggingface-cli login') e aceite os termos em "
                f"https://hf.co/{self.model_id}"
            )

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        self.check_ready()
        from pyannote.audio import Pipeline

        token = find_hf_token()
        DIARIZATION_CACHE.mkdir(parents=True, exist_ok=True)
        try:
            try:
                pipeline = Pipeline.from_pretrained(
                    self.model_id, token=token, cache_dir=str(DIARIZATION_CACHE),
                )
            except TypeError:  # pyannote.audio 3.x
                pipeline = Pipeline.from_pretrained(
                    self.model_id, use_auth_token=token,
                    cache_dir=str(DIARIZATION_CACHE),
                )
        except Exception as e:
            msg = str(e)
            if token and token in msg:
                msg = msg.replace(token, "***")
            if any(k in msg.lower() for k in ("gated", "restricted", "401", "403")):
                raise DiarizationUnavailable(
                    "Acesso negado ao modelo de diarização: aceite os termos em "
                    f"https://hf.co/{self.model_id} com a conta do token "
                    "configurado em HF_TOKEN."
                ) from None
            raise DiarizationUnavailable(
                f"Falha ao carregar o modelo {self.model_id}: {msg[:200]}"
            ) from None
        if pipeline is None:  # 3.x devolve None quando o acesso falha
            raise DiarizationUnavailable(
                f"Modelo {self.model_id} não pôde ser carregado: confira "
                f"HF_TOKEN e o aceite dos termos em https://hf.co/{self.model_id}"
            )
        self._move_to_device(pipeline)
        self._pipeline = pipeline
        return pipeline

    def _move_to_device(self, pipeline) -> None:
        try:
            import torch
        except ImportError:  # pragma: no cover - pyannote sempre traz torch
            return
        wanted = self.device
        if wanted == "auto":
            wanted = "cuda" if torch.cuda.is_available() else "cpu"
        if wanted != "cpu" and hasattr(pipeline, "to"):
            pipeline.to(torch.device(wanted))

    # -- execução -----------------------------------------------------------

    def diarize(self, wav_path: str | Path, *, num_speakers: int | None = None,
                min_speakers: int | None = None,
                max_speakers: int | None = None,
                exclusive: bool | None = None) -> list[SpeakerTurn]:
        """Diariza um WAV PCM16 (idealmente 16 kHz mono).

        Args:
            num_speakers: Nº exato de falantes, se conhecido (mais preciso).
            min_speakers / max_speakers: Faixa, se o exato for desconhecido.
            exclusive: Uma pessoa por instante (bom para legendas). None =
                ``settings.diarization_exclusive``.

        Returns:
            Turnos ordenados por início, com rótulos ``SPEAKER_NN``.
        """
        if exclusive is None:
            exclusive = settings.diarization_exclusive
        pipeline = self._load()
        audio, rate = _read_wav(wav_path)
        try:
            import torch
            waveform = torch.from_numpy(audio)
        except ImportError:  # pragma: no cover - injeção em testes
            waveform = audio
        kwargs = {k: v for k, v in (("num_speakers", num_speakers),
                                    ("min_speakers", min_speakers),
                                    ("max_speakers", max_speakers)) if v}
        output = pipeline({"waveform": waveform, "sample_rate": rate}, **kwargs)

        if hasattr(output, "speaker_diarization"):  # pyannote.audio >= 4
            annotation = (output.exclusive_speaker_diarization if exclusive
                          else output.speaker_diarization)
            turns = _annotation_to_turns(annotation)
        else:
            turns = _annotation_to_turns(output)
            if exclusive:
                turns = make_exclusive(turns)
        turns = normalize_labels(turns)
        _logger.info("offline_diarization_done", model=self.model_id,
                     turns=len(turns),
                     speakers=len({t.speaker for t in turns}))
        return turns
