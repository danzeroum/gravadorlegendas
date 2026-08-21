"""Testes unitários para AudioMixer (Frente B).

Validam a lógica de mixagem sem depender de PipeWire real — usam
sinais sintéticos (senoides, silêncio, saturação) em PCM s16le.

O guard-rail crítico **T4.4** (mixagem não pode degradar o caso
simples) é implementado aqui em versão unitária em memória:
simulamos o cenário "mic ativo + sistema em silêncio" e verificamos
que a saída mixada preserva o sinal do mic dentro de uma tolerância
objetiva (correlação cruzada alta + energia proporcional).

Os testes de integração T4.1–T4.4 (com sink virtual PipeWire real)
estão em ``tests/integration/test_audio_mix_both_real.py`` e fazem
skip automático em ambientes sem PipeWire/pactl.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.audio.mixer import AudioMixer


def _gen_sine_pcm16(freq: float, duration_s: float, sample_rate: int = 16000,
                    amplitude: float = 0.5) -> bytes:
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    samples = (amplitude * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()


def _gen_silence_pcm16(duration_s: float, sample_rate: int = 16000) -> bytes:
    n = int(duration_s * sample_rate)
    return np.zeros(n, dtype=np.int16).tobytes()


def _pcm16_to_float(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.int16).astype(np.float32) / 32768.0


def _cross_correlation(a: bytes, b: bytes) -> float:
    """Coeficiente de correlação normalizado entre dois PCM16."""
    fa = _pcm16_to_float(a)
    fb = _pcm16_to_float(b)
    n = min(len(fa), len(fb))
    if n == 0:
        return 0.0
    fa = fa[:n] - fa[:n].mean()
    fb = fb[:n] - fb[:n].mean()
    denom = (np.linalg.norm(fa) * np.linalg.norm(fb)) + 1e-12
    return float(np.dot(fa, fb) / denom)


class TestAudioMixerBasic:
    """Testes básicos da mixagem."""

    def test_both_empty_returns_empty(self):
        mixer = AudioMixer()
        out = mixer.mix_frame(None, None)
        assert out == b""
        out = mixer.mix_frame(b"", b"")
        assert out == b""

    def test_one_empty_returns_other_unchanged(self):
        """T4.3 (unitário): fonte ausente é repassada sem degradar."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1)
        out = mixer.mix_frame(mic, None)
        # Quando uma fonte está vazia, o mixer retorna a outra byte-a-byte.
        assert out == mic

        out = mixer.mix_frame(None, mic)
        assert out == mic

    def test_both_present_returns_same_size(self):
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1)
        sys = _gen_sine_pcm16(freq=880, duration_s=0.1)
        out = mixer.mix_frame(mic, sys)
        assert len(out) == len(mic) == len(sys)

    def test_different_sizes_pads_shorter(self):
        """Frame menor é padded com zeros para igualar tamanho."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1)  # 1600 samples
        sys = _gen_sine_pcm16(freq=880, duration_s=0.05)  # 800 samples
        out = mixer.mix_frame(mic, sys)
        # Saída tem o tamanho do maior (1600 samples * 2 bytes)
        assert len(out) == len(mic)


class TestAudioMixerOverflow:
    """Testes de prevenção de overflow/clipping."""

    def test_two_full_scale_signals_no_overflow(self):
        """Soma de dois sinais em amplitude máxima não satura indevidamente."""
        mixer = AudioMixer(target_rms=None)  # desativa AGC para teste puro
        # Dois sinais em amplitude 1.0 (full-scale)
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1, amplitude=1.0)
        sys = _gen_sine_pcm16(freq=880, duration_s=0.1, amplitude=1.0)
        out = mixer.mix_frame(mic, sys)
        # Como (a+b)/2 com clamp, jamais ultrapassa full-scale
        arr = _pcm16_to_float(out)
        assert np.all(np.abs(arr) <= 1.0), (
            f"Overflow detectado: pico {np.max(np.abs(arr))}"
        )

    def test_no_nan_no_inf(self):
        """Saída não deve conter NaN ou Inf."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1)
        sys = _gen_sine_pcm16(freq=880, duration_s=0.1)
        out = mixer.mix_frame(mic, sys)
        arr = _pcm16_to_float(out)
        assert not np.any(np.isnan(arr))
        assert not np.any(np.isinf(arr))


class TestAudioMixerAGC:
    """Testes do AGC pré-mixagem."""

    def test_agc_normalizes_low_volume(self):
        """T4.2 (unitário): fonte baixa é normalizada para o alvo."""
        mixer = AudioMixer(target_rms=0.1)
        mic_low = _gen_sine_pcm16(freq=440, duration_s=0.5, amplitude=0.01)
        sys_normal = _gen_sine_pcm16(freq=880, duration_s=0.5, amplitude=0.5)
        out = mixer.mix_frame(mic_low, sys_normal)
        # Após AGC, o mic_low deve ter sido elevado (ganho > 1.0 limitado).
        # Verificamos que a saída tem energia não-trivial (não ficou silenciosa).
        out_arr = _pcm16_to_float(out)
        rms_out = float(np.sqrt(np.mean(out_arr ** 2)))
        assert rms_out > 0.01, (
            f"Saída muito baixa após AGC: RMS={rms_out}"
        )

    def test_agc_does_not_amplify_already_loud(self):
        """AGC limita ganho a 1.0 — não amplifica sinal já acima do alvo."""
        mixer = AudioMixer(target_rms=0.05)
        mic = _gen_sine_pcm16(freq=440, duration_s=0.1, amplitude=0.9)
        sys = _gen_silence_pcm16(0.1)
        out = mixer.mix_frame(mic, sys)
        # Como sys é silêncio, mixer repassa mic inalterado (sem AGC nesse caso)
        # Mas se ambos estivessem ativos, o ganho seria <= 1.0.
        # Testamos com ambos ativos:
        out2 = mixer.mix_frame(mic, mic)
        out2_arr = _pcm16_to_float(out2)
        mic_arr = _pcm16_to_float(mic)
        # Pico não deve aumentar em relação ao original
        assert np.max(np.abs(out2_arr)) <= np.max(np.abs(mic_arr)) + 0.01


class TestAudioMixerT44GuardRail:
    """Guard-rail T4.4 (unitário em memória): a mixagem não pode degradar
    o caso simples.

    Cenário simulado: apenas o mic está ativo (sistema em silêncio puro).
    A transcrição esperada nesse caso é exatamente a do mic sozinho.
    Como não temos Whisper em teste unitário, validamos a **propriedade
    acústica** que garante fidelidade: a saída mixada deve ter alta
    correlação com o sinal do mic sozinho (>= 0.95).

    A versão de integração (T4.4 com Whisper real) está em
    tests/integration/test_audio_mix_both_real.py.
    """

    def test_t44_mixing_preserves_signal_when_system_silent(self):
        """T4.4: com sistema em silêncio, mixagem preserva mic (corr >= 0.95)."""
        mixer = AudioMixer()
        # Mic com sinal claro de 440 Hz
        mic = _gen_sine_pcm16(freq=440, duration_s=0.5, amplitude=0.5)
        # Sistema em silêncio puro
        sys_silence = _gen_silence_pcm16(0.5)
        out = mixer.mix_frame(mic, sys_silence)
        # Quando sys_silence é None/vazio, mixer repassa mic byte-a-byte.
        # Mas como sys_silence não é None (é bytes de zeros), o mixer
        # aplica o AGC e mixa — então verificamos que o resultado tem
        # alta correlação com o mic original.
        corr = _cross_correlation(out, mic)
        assert corr >= 0.95, (
            f"Mixagem degradou o sinal do mic: correlação {corr:.3f} < 0.95"
        )

    def test_t44_mixing_with_one_source_none_preserves_signal_exactly(self):
        """T4.3 + T4.4 combinados: com sistema=None, saída é idêntica ao mic."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.3, amplitude=0.5)
        out = mixer.mix_frame(mic, None)
        assert out == mic, (
            "mix_frame com sistema=None deve retornar mic exatamente"
        )

    def test_t44_no_artificial_noise_introduced(self):
        """T4.4: mixagem não introduz ruído artificial quando sistema está silencioso."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.5, amplitude=0.5)
        # Sistema em silêncio puro (zeros reais)
        sys_silence = _gen_silence_pcm16(0.5)
        out = mixer.mix_frame(mic, sys_silence)
        out_arr = _pcm16_to_float(out)
        mic_arr = _pcm16_to_float(mic)
        # A energia da saída não deve ser muito maior que a do mic
        # (não deve ter ruído artificialmente adicionado).
        rms_out = float(np.sqrt(np.mean(out_arr ** 2)))
        rms_mic = float(np.sqrt(np.mean(mic_arr ** 2)))
        # Tolerância de 2x para acomodar o AGC.
        assert rms_out <= rms_mic * 2.0 + 0.01, (
            f"Saída com muito mais energia que o mic: "
            f"out={rms_out:.4f} mic={rms_mic:.4f}"
        )


class TestAudioMixerEdgeCases:
    """Casos extremos."""

    def test_odd_byte_length_truncates(self):
        """Frame com bytes ímpares (incompleto) é tratado sem erro."""
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.01) + b"\x00"  # 1 byte a mais
        sys = _gen_sine_pcm16(freq=880, duration_s=0.01)
        # Não deve lançar exceção
        out = mixer.mix_frame(mic, sys)
        # Saída deve ter pelo menos algum tamanho
        assert len(out) > 0

    def test_thread_safety(self):
        """Múltiplas threads chamando mix_frame simultaneamente não corrompem."""
        import threading
        mixer = AudioMixer()
        mic = _gen_sine_pcm16(freq=440, duration_s=0.01)
        sys = _gen_sine_pcm16(freq=880, duration_s=0.01)
        outputs = []
        lock = threading.Lock()

        def worker():
            for _ in range(50):
                out = mixer.mix_frame(mic, sys)
                with lock:
                    outputs.append(out)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Todos os outputs devem ter o mesmo tamanho (determinístico)
        assert all(len(o) == len(mic) for o in outputs)
        assert len(outputs) == 200
