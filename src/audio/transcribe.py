"""Transcrição de áudio com faster-whisper em processo separado.

Usa multiprocessing.Queue para comunicação com o processo
principal, evitando bloqueio da UI.
"""
import multiprocessing
import queue
import time
from pathlib import Path

import numpy as np
import structlog

_logger = structlog.get_logger()

# No Fedora/Linux, usar fork() para criar o processo de transcrição a partir
# de um processo pai multi-threaded (torch/ctranslate2/tkinter) pode
# deadlockar o filho. "spawn" reimporta o módulo num interpretador limpo e
# evita esse deadlock. Aplicado globalmente porque o app e os testes criam
# o TranscriberProcess depois de iniciar threads.
if multiprocessing.get_start_method(allow_none=True) != "spawn":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except (RuntimeError, ValueError):  # pragma: no cover
        pass


# Cache único de modelos Whisper. O setup (`scripts/setup_audio_models.py`)
# baixa para o MESMO diretório, então o app não re-baixa e os testes de
# integração verificam exatamente o mesmo local.
WHISPER_DOWNLOAD_ROOT = Path.home() / ".cache" / "gravador" / "audio" / "whisper"


def whisper_model_dir(model_size: str) -> Path:
    """Diretório (layout snapshot do HF Hub) do modelo no cache do app."""
    return WHISPER_DOWNLOAD_ROOT / f"models--Systran--faster-whisper-{model_size}"


class TranscriberProcess(multiprocessing.Process):
    """Processo separado para transcrição com faster-whisper.

    Args:
        input_queue: Queue que recebe chunks de áudio (bytes PCM16).
        output_queue: Queue onde resultados de transcrição são enviados.
        model_size: Tamanho do modelo Whisper (tiny, base, small, etc.).
        chunk_duration: Duração alvo de cada batch em segundos.
        language: Idioma forçado do Whisper (ex.: "pt"). Padrão "pt" para
            o mercado-alvo; o pipeline captura PCM pt-BR.
        task: Tarefa do Whisper ("transcribe" ou "translate"). Sempre
            "transcribe" para legendagem.
        beam_size: Tamanho do beam do Whisper. Em voz sintética/robótica
            (espeak) o beam=1 + temperature=0 transcreve com mais fidelidade;
            em fala humana natural beam=5 costuma ser melhor.
        temperature: Temperatura de amostragem. 0.0 = greedy, determinístico.
        vad_filter: Silero VAD antes da transcrição. Elimina as alucinações
            repetitivas do Whisper em silêncio ("e o que é o que é...") sem
            descartar a fala real; habilitado por padrão.
    """

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
        model_size: str = "base",
        chunk_duration: float = 7.0,
        language: str = "pt",
        task: str = "transcribe",
        beam_size: int = 1,
        temperature: float = 0.0,
        vad_filter: bool = True,
    ):
        super().__init__(daemon=True)
        self._input = input_queue
        self._output = output_queue
        self._model_size = model_size
        self._chunk_size = int(16000 * 2 * chunk_duration)
        self._language = language
        self._task = task
        self._beam_size = beam_size
        self._temperature = temperature
        self._vad_filter = vad_filter
        self._stop_event = multiprocessing.Event()

    def stop(self):
        """Sinaliza para o processo parar."""
        self._stop_event.set()

    def run(self):
        """Loop principal de transcrição."""
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(
                self._model_size,
                device="cpu",
                download_root=str(WHISPER_DOWNLOAD_ROOT),
            )
        except ImportError:
            self._output.put({"error": "faster-whisper não instalado"})
            return
        except Exception as e:
            self._output.put({"error": f"Erro ao carregar modelo: {e}"})
            return

        audio_buffer = b""
        session_start = None
        batch_index = 0

        while not self._stop_event.is_set():
            try:
                chunk = self._input.get(timeout=0.5)
            except queue.Empty:
                continue

            if session_start is None:
                session_start = time.monotonic()

            audio_buffer += chunk

            if len(audio_buffer) >= self._chunk_size:
                buf = audio_buffer[:self._chunk_size]
                audio_buffer = audio_buffer[self._chunk_size:]

                elapsed = time.monotonic() - session_start
                batch_dur = self._chunk_size / (16000.0 * 2)
                seg_start = round(elapsed - batch_dur, 2)
                seg_end = round(elapsed, 2)
                batch_index += 1

                # Validação do formato PCM esperado: s16le mono 16kHz.
                # O buffer é montado a partir de chunks de 960 bytes
                # (480 frames x 2 bytes) com sample_rate=16000 fixo. Qualquer
                # desvio (rate/canais incorretos) quebra esta assunção.
                if len(buf) % 2 != 0 or len(buf) == 0:
                    _logger.error(
                        "stt_batch_invalid_pcm",
                        batch=batch_index,
                        bytes=len(buf),
                    )
                    continue

                audio_array = (
                    np.frombuffer(buf, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )

                # Diagnóstico do áudio que entra no Whisper: duração, RMS e
                # pico. Essencial para distinguir falha de qualidade (sinal
                # baixo/clipado) de falha de transcrição.
                _dur = len(audio_array) / 16000.0
                _rms = float(np.sqrt(np.mean(audio_array ** 2)))
                _peak = float(np.max(np.abs(audio_array)))

                try:
                    segments, _ = model.transcribe(
                        audio_array,
                        language=self._language,
                        task=self._task,
                        beam_size=self._beam_size,
                        temperature=self._temperature,
                        vad_filter=self._vad_filter,
                    )
                    # Frente D: coleta segmentos individuais com timestamp
                    # absoluto (relativo ao início da sessão do processo).
                    # O offset por batch já está embutido em seg_start.
                    seg_list = []
                    text_parts = []
                    for seg in segments:
                        seg_text = (seg.text or "").strip()
                        if not seg_text:
                            # T6.6: nunca emitir segmento vazio (silêncio)
                            continue
                        # seg.start/seg.end são relativos ao batch atual;
                        # somar seg_start para torná-los absolutos da sessão.
                        abs_start = round(seg_start + float(seg.start), 3)
                        abs_end = round(seg_start + float(seg.end), 3)
                        seg_list.append({
                            "start": abs_start,
                            "end": abs_end,
                            "text": seg_text,
                        })
                        text_parts.append(seg_text)
                    text = " ".join(text_parts)
                    _logger.info(
                        "stt_batch_done",
                        batch=batch_index,
                        duration=round(_dur, 2),
                        rms=round(_rms, 4),
                        peak=round(_peak, 4),
                        text=text.strip(),
                        n_segments=len(seg_list),
                    )
                    if text.strip():
                        self._output.put({
                            "text": text.strip(),
                            "start": seg_start,
                            "end": seg_end,
                            "batch": batch_index,
                            # Frente D: lista de segmentos com timestamp
                            # absoluto por segmento, para o exportador SRT/VTT.
                            "segments": seg_list,
                        })
                except Exception as e:
                    self._output.put({"error": str(e)})
