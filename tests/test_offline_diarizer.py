"""DIA-04..07 — diarizador offline (Frente E, D-018).

Sem modelo real: pipelines falsos imitam a saída do pyannote.audio 3.x
(``Annotation``) e 4.x (``DiarizeOutput``). O teste com modelo real fica
em tests/fidelity (marker ``requires_hf_token``).
"""
import sys
import types
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from src.audio import offline_diarizer as od
from src.audio.offline_diarizer import (
    DiarizationUnavailable, OfflineDiarizer, SpeakerTurn, make_exclusive,
    normalize_labels,
)


# ---------------------------------------------------------------------------
# make_exclusive / normalize_labels (puras)
# ---------------------------------------------------------------------------

def T(s, a, b):
    return SpeakerTurn(s, a, b)


def test_exclusive_without_overlap_is_identity():
    turns = [T("A", 0, 2), T("B", 2.5, 4)]
    assert make_exclusive(turns) == turns


def test_exclusive_later_starter_takes_the_floor():
    assert make_exclusive([T("A", 0, 3), T("B", 2, 5)]) == [T("A", 0, 2), T("B", 2, 5)]


def test_exclusive_interjection_then_previous_resumes():
    # B fala "uhum" no meio da fala longa de A.
    assert make_exclusive([T("A", 0, 10), T("B", 4, 5)]) == [
        T("A", 0, 4), T("B", 4, 5), T("A", 5, 10),
    ]


def test_exclusive_merges_same_speaker_and_drops_empty():
    assert make_exclusive([T("A", 0, 2), T("A", 1, 3), T("B", 5, 5)]) == [T("A", 0, 3)]


def _union_length(turns):
    total, end = 0.0, -1.0
    for t in sorted(turns, key=lambda t: t.start):
        if t.start > end:
            total += t.end - t.start
            end = t.end
        elif t.end > end:
            total += t.end - end
            end = t.end
    return total


def test_exclusive_properties():
    """Sem sobreposição, ordenado, cobre a união e só usa falantes da entrada.

    Propriedade sobre 60 entradas aleatórias determinísticas (seed fixa);
    hypothesis não é dependência do job ``test`` do CI.
    """
    rng = np.random.default_rng(1234)
    for _ in range(60):
        turns = [
            T(str(rng.choice(["A", "B", "C"])), float(a), float(a + d))
            for a, d in zip(rng.uniform(0, 60, rng.integers(0, 13)),
                            rng.uniform(0.01, 10, 13))
        ]
        out = make_exclusive(turns)
        for x, y in zip(out, out[1:]):
            assert x.end <= y.start
        assert sum(t.end - t.start for t in out) == pytest.approx(
            _union_length(turns), abs=1e-6)
        assert {t.speaker for t in out} <= {t.speaker for t in turns}


def test_normalize_labels_by_first_speech():
    turns = [T("spk_7", 3, 4), T("spk_2", 0, 1), T("spk_7", 5, 6), T("x", 1.5, 2)]
    assert normalize_labels(turns) == [
        T("SPEAKER_00", 0, 1), T("SPEAKER_01", 1.5, 2),
        T("SPEAKER_02", 3, 4), T("SPEAKER_02", 5, 6),
    ]


# ---------------------------------------------------------------------------
# OfflineDiarizer com pipeline falso
# ---------------------------------------------------------------------------

class FakeAnnotation:
    def __init__(self, tracks):
        self._tracks = tracks

    def itertracks(self, yield_label=True):
        for label, a, b in self._tracks:
            yield SimpleNamespace(start=a, end=b), None, label


class FakePipeline:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def __call__(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return self.output


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes((np.ones(16000, np.int16) * 1000).tobytes())
    return path


OVERLAPPING = [("B", 0.0, 3.0), ("A", 2.0, 5.0)]


def test_v3_annotation_exclusive_applies_make_exclusive(wav):
    pipe = FakePipeline(FakeAnnotation(OVERLAPPING))
    turns = OfflineDiarizer(pipeline=pipe).diarize(wav, exclusive=True)
    assert turns == [T("SPEAKER_00", 0.0, 2.0), T("SPEAKER_01", 2.0, 5.0)]


def test_v3_annotation_non_exclusive_keeps_overlap(wav):
    pipe = FakePipeline(FakeAnnotation(OVERLAPPING))
    turns = OfflineDiarizer(pipeline=pipe).diarize(wav, exclusive=False)
    assert turns == [T("SPEAKER_00", 0.0, 3.0), T("SPEAKER_01", 2.0, 5.0)]


def test_v4_output_uses_native_exclusive_annotation(wav):
    out = SimpleNamespace(
        speaker_diarization=FakeAnnotation(OVERLAPPING),
        exclusive_speaker_diarization=FakeAnnotation([("B", 0.0, 2.5), ("A", 2.5, 5.0)]),
    )
    pipe = FakePipeline(out)
    d = OfflineDiarizer(pipeline=pipe)
    assert d.diarize(wav, exclusive=True) == [T("SPEAKER_00", 0, 2.5), T("SPEAKER_01", 2.5, 5)]
    assert d.diarize(wav, exclusive=False)[0] == T("SPEAKER_00", 0, 3.0)


def test_waveform_in_memory_and_speaker_kwargs(wav):
    pipe = FakePipeline(FakeAnnotation([]))
    OfflineDiarizer(pipeline=pipe).diarize(wav, num_speakers=3)
    OfflineDiarizer(pipeline=pipe).diarize(wav, min_speakers=2, max_speakers=4)
    audio, kwargs = pipe.calls[0]
    assert audio["sample_rate"] == 16000
    assert tuple(audio["waveform"].shape) == (1, 16000)
    assert kwargs == {"num_speakers": 3}
    assert pipe.calls[1][1] == {"min_speakers": 2, "max_speakers": 4}


# ---------------------------------------------------------------------------
# check_ready / carregamento: mensagens acionáveis, token nunca exposto
# ---------------------------------------------------------------------------

def test_check_ready_without_pyannote(monkeypatch):
    monkeypatch.setattr(od.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(DiarizationUnavailable, match=r"\.\[diarization\]"):
        OfflineDiarizer(model_id="m/x").check_ready()


def test_check_ready_without_token(monkeypatch):
    monkeypatch.setattr(od.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(od, "find_hf_token", lambda: None)
    with pytest.raises(DiarizationUnavailable, match="HF_TOKEN") as exc:
        OfflineDiarizer(model_id="pyannote/x").check_ready()
    assert "hf.co/pyannote/x" in str(exc.value)


def test_find_hf_token_prefers_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_env_value")
    assert od.find_hf_token() == "hf_env_value"


def _fake_pyannote(monkeypatch, from_pretrained):
    mod = types.ModuleType("pyannote.audio")
    mod.Pipeline = SimpleNamespace(from_pretrained=from_pretrained)
    monkeypatch.setitem(sys.modules, "pyannote.audio", mod)
    monkeypatch.setattr(OfflineDiarizer, "check_ready", lambda self: None)
    monkeypatch.setattr(od, "DIARIZATION_CACHE", od.Path("/tmp") / "gravador_test_diar")


def test_gated_model_message_hides_token(monkeypatch, wav):
    secret = "hf_SEGREDO_NAO_PODE_APARECER_123456"
    monkeypatch.setattr(od, "find_hf_token", lambda: secret)

    def boom(model, **kw):
        raise RuntimeError(f"401 Client Error: gated repo (token={secret})")
    _fake_pyannote(monkeypatch, boom)
    with pytest.raises(DiarizationUnavailable) as exc:
        OfflineDiarizer(model_id="pyannote/x").diarize(wav)
    assert secret not in str(exc.value)
    assert "aceite os termos" in str(exc.value)


def test_v3_signature_fallback_and_none_result(monkeypatch, wav):
    monkeypatch.setattr(od, "find_hf_token", lambda: "t")
    seen = []

    def v3_style(model, use_auth_token=None, cache_dir=None, **kw):
        if kw:
            raise TypeError("unexpected keyword 'token'")
        seen.append(use_auth_token)
        return None  # 3.x devolve None quando o acesso falha
    _fake_pyannote(monkeypatch, v3_style)
    with pytest.raises(DiarizationUnavailable, match="não pôde ser carregado"):
        OfflineDiarizer(model_id="pyannote/x", device="cpu").diarize(wav)
    assert seen == ["t"]


def test_default_model_matches_installed_major(monkeypatch):
    import importlib.metadata as md
    monkeypatch.setattr(md, "version", lambda name: "4.0.7")
    assert od.default_model() == od.MODEL_V4
    monkeypatch.setattr(md, "version", lambda name: "3.3.2")
    assert od.default_model() == od.MODEL_V3


# ---------------------------------------------------------------------------
# DiarizationProcess.diarize_file mantém o contrato list[dict] (R6)
# ---------------------------------------------------------------------------

def test_diarize_file_delegates_and_keeps_contract(monkeypatch, wav):
    import multiprocessing

    from src.audio.diarize import DiarizationProcess

    monkeypatch.setattr(
        OfflineDiarizer, "diarize",
        lambda self, path, **kw: [T("SPEAKER_00", 0.123, 1.987)],
    )
    dp = DiarizationProcess(multiprocessing.Queue(), multiprocessing.Queue())
    assert dp.diarize_file(str(wav)) == [
        {"speaker": "SPEAKER_00", "start": 0.12, "end": 1.99},
    ]
