"""Transcrição de áudio com faster-whisper em processo separado.

Usa multiprocessing.Queue para comunicação com o processo
principal, evitando bloqueio da UI.
"""
import multiprocessing
import queue
import time
import numpy as np


class TranscriberProcess(multiprocessing.Process):
    """Processo separado para transcrição com faster-whisper.

    Args:
        input_queue: Queue que recebe chunks de áudio (bytes PCM16).
        output_queue: Queue onde resultados de transcrição são enviados.
        model_size: Tamanho do modelo Whisper (tiny, base, small, etc.).
        chunk_duration: Duração alvo de cada batch em segundos.
    """

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
        model_size: str = "base",
        chunk_duration: float = 1.0,
        language: str = "pt",
    ):
        super().__init__(daemon=True)
        self._input = input_queue
        self._output = output_queue
        self._model_size = model_size
        self._chunk_size = int(16000 * 2 * chunk_duration)
        self._language = language
        self._stop_event = multiprocessing.Event()

    def stop(self):
        """Sinaliza para o processo parar."""
        self._stop_event.set()

    def run(self):
        """Loop principal de transcrição."""
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self._model_size, device="cpu")
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
                seg_start = round(elapsed - 1.0, 2)
                seg_end = round(elapsed, 2)
                batch_index += 1

                audio_array = (
                    np.frombuffer(buf, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )

                try:
                    segments, _ = model.transcribe(audio_array, language=self._language)
                    text = " ".join(seg.text for seg in segments)
                    if text.strip():
                        self._output.put({
                            "text": text.strip(),
                            "start": seg_start,
                            "end": seg_end,
                            "batch": batch_index,
                        })
                except Exception as e:
                    self._output.put({"error": str(e)})
