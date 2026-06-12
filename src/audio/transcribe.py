"""Transcrição de áudio com faster-whisper em processo separado.

Usa multiprocessing.Queue para comunicação com o processo
principal, evitando bloqueio da UI.
"""
import multiprocessing
import queue
import numpy as np


class TranscriberProcess(multiprocessing.Process):
    """Processo separado para transcrição com faster-whisper.

    Args:
        input_queue: Queue que recebe chunks de áudio (bytes PCM16).
        output_queue: Queue onde resultados de transcrição são enviados.
        model_size: Tamanho do modelo Whisper (tiny, base, small, etc.).
    """

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
        model_size: str = "base",
    ):
        super().__init__(daemon=True)
        self._input = input_queue
        self._output = output_queue
        self._model_size = model_size
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

        while not self._stop_event.is_set():
            try:
                chunk = self._input.get(timeout=0.5)
            except queue.Empty:
                continue

            audio_buffer += chunk

            if len(audio_buffer) >= 16000 * 2:
                audio_array = (
                    np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
                audio_buffer = b""

                try:
                    segments, _ = model.transcribe(audio_array, language="pt")
                    text = " ".join(seg.text for seg in segments)
                    if text.strip():
                        self._output.put({"text": text.strip()})
                except Exception as e:
                    self._output.put({"error": str(e)})
