"""Controle da importação de arquivo em segundo plano (Frente J).

Sem imports de UI: testável em ambiente headless. A janela chama
``poll()`` periodicamente (``root.after``) e reage aos eventos.

O trabalho pesado (decodificar, Whisper, pyannote) roda num processo
``spawn`` separado — a UI não trava e um travamento do modelo não derruba
a janela; ``cancel()`` pede parada cooperativa e ``terminate()`` encerra à
força (fechamento da janela).
"""
from __future__ import annotations

import multiprocessing
import queue
import time
from typing import Callable

from src.audio.file_pipeline import run_import_job, transcript_from_dict

# Depois de pedir cancelamento, quanto esperar antes de matar o processo.
_CANCEL_GRACE_S = 5.0


class ImportJob:
    """Uma importação: inicia, recebe progresso, cancela, termina.

    Args:
        path: Arquivo de áudio/vídeo.
        options: Repassadas a ``transcribe_audio_file`` (``model_size``,
            ``num_speakers``…). Precisam ser serializáveis (spawn).
        process_factory / queue_factory / event_factory: Injeção para
            testes (padrão: contexto ``spawn`` do multiprocessing).
    """

    def __init__(self, path: str, options: dict | None = None, *,
                 process_factory: Callable | None = None,
                 queue_factory: Callable | None = None,
                 event_factory: Callable | None = None):
        ctx = multiprocessing.get_context("spawn")
        self.path = path
        self.options = dict(options or {})
        self._process_factory = process_factory or (
            lambda target, args: ctx.Process(target=target, args=args, daemon=True))
        self._queue = (queue_factory or ctx.Queue)()
        self._cancel = (event_factory or ctx.Event)()
        self._process = None
        self._cancel_requested_at: float | None = None
        self.done = False
        self.progress = 0.0
        self.stage = ""

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested_at is not None

    def start(self) -> None:
        self._process = self._process_factory(
            run_import_job, (self.path, self.options, self._queue, self._cancel))
        self._process.start()

    def cancel(self) -> None:
        """Pede parada cooperativa (checada entre segmentos)."""
        if not self.done and self._cancel_requested_at is None:
            self._cancel.set()
            self._cancel_requested_at = time.monotonic()

    def terminate(self) -> None:
        """Encerra à força (ex.: fechando a janela)."""
        self._cancel.set()
        proc = self._process
        if proc is not None and proc.is_alive() and hasattr(proc, "terminate"):
            proc.terminate()
        self.done = True

    def poll(self) -> list[dict]:
        """Eventos novos. Converte ``result`` em ``FileTranscript``.

        Eventos: ``{"type": "progress", "progress", "stage"}``,
        ``{"type": "result", "transcript"}``, ``{"type": "cancelled"}``,
        ``{"type": "error", "message"}``. Depois de um evento final,
        ``done`` fica True.
        """
        # Estado do processo ANTES de drenar: se já tinha morrido, tudo o
        # que ele publicou está na fila; se a fila não trouxer evento final,
        # foi um crash (sem corrida com um resultado publicado no fim).
        exited = self._process is not None and not self._process.is_alive()
        events: list[dict] = []
        while not self.done:
            try:
                msg = self._queue.get_nowait()
            except (queue.Empty, OSError, ValueError):
                break
            events.append(self._to_event(msg))

        if not self.done and exited:
            self.done = True
            events.append({"type": "error",
                           "message": "O processo de transcrição terminou inesperadamente."})
        if (not self.done and self._cancel_requested_at is not None
                and time.monotonic() - self._cancel_requested_at > _CANCEL_GRACE_S):
            self.terminate()
            events.append({"type": "cancelled"})
        return events

    def _to_event(self, msg: dict) -> dict:
        if "progress" in msg:
            self.progress, self.stage = msg["progress"], msg["stage"]
            return {"type": "progress", "progress": self.progress, "stage": self.stage}
        self.done = True
        if "result" in msg:
            return {"type": "result", "transcript": transcript_from_dict(msg["result"])}
        if msg.get("cancelled"):
            return {"type": "cancelled"}
        return {"type": "error", "message": msg.get("error", "erro desconhecido")}


# ---------------------------------------------------------------------------
# Apresentação (pura) usada pela janela
# ---------------------------------------------------------------------------

MAX_PARTICIPANTS = 20
WHISPER_CHOICES = ("tiny", "base", "small", "medium", "large-v3")
FILE_TYPES = [
    ("Áudio e vídeo", "*.wav *.mp3 *.m4a *.mp4 *.ogg *.opus *.flac *.webm"),
    ("Todos os arquivos", "*"),
]


def parse_participants(text: str) -> int | None:
    """Campo "Nº de participantes": vazio = desconhecido (None).

    Raises:
        ValueError: com mensagem para o usuário.
    """
    text = (text or "").strip()
    if not text:
        return None
    if not text.isdigit():
        raise ValueError("Informe um número inteiro de participantes (ou deixe vazio).")
    n = int(text)
    if not 1 <= n <= MAX_PARTICIPANTS:
        raise ValueError(f"O número de participantes deve ser de 1 a {MAX_PARTICIPANTS}.")
    return n


def format_transcript_lines(transcript, display_name: Callable[[str | None], str]) -> list[str]:
    """Linhas do painel: ``[HH:MM:SS] ● Participante A: texto``.

    ``display_name(rótulo)`` devolve o prefixo do falante (o mesmo usado na
    transcrição ao vivo, ex.: ``"● Juliana: "``) ou ``""``.
    """
    from src.storage.subtitle_exporter import format_clock

    return [f"[{format_clock(s.start)}] {display_name(s.speaker)}{s.text}"
            for s in transcript.segments]


def progress_text(progress: float, stage: str) -> str:
    return f"{stage.rstrip('…').rstrip('.')} — {int(round(progress * 100))}%"
