import silero_vad as _real_silero
from src.audio.vad import VoiceActivityDetector


class TestVoiceActivityDetector:
    def test_load_idempotent(self):
        v = VoiceActivityDetector()
        v._model = "already_loaded"
        v.load()
        assert v._model == "already_loaded"

    def test_is_speech_with_mock(self, monkeypatch):
        def mock_fn(*a, **kw):
            return [{"start": 10, "end": 100}]
        monkeypatch.setattr(_real_silero, "get_speech_timestamps", mock_fn)
        v = VoiceActivityDetector()
        v._model = "mock_model"
        assert v.is_speech(b"\x00\x01\x02\x03") is True

    def test_is_speech_false_with_mock(self, monkeypatch):
        def mock_fn(*a, **kw):
            return []
        monkeypatch.setattr(_real_silero, "get_speech_timestamps", mock_fn)
        v = VoiceActivityDetector()
        v._model = "mock_model"
        assert v.is_speech(b"\x00\x01") is False
