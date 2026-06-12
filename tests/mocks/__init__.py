"""Mock helpers para testes dos módulos de áudio."""


class MockSileroVad:
    """Simula silero_vad.get_speech_timestamps."""

    def __init__(self, has_speech: bool = True):
        self._has_speech = has_speech

    def get_speech_timestamps(self, audio, model, threshold=0.5):
        if self._has_speech:
            start = int(len(audio) * 0.1)
            end = int(len(audio) * 0.9)
            return [{"start": start, "end": end}]
        return []


class MockDiarization:
    """Simula diart.OnlineSpeakerDiarization."""

    def __init__(self, segments: list | None = None):
        self._segments = segments or [
            {"speaker": "speaker_0", "start": 0.0, "end": 3.0},
            {"speaker": "speaker_1", "start": 3.5, "end": 7.0},
        ]

    def __call__(self, source):
        return self._segments

    def itertracks(self, yield_label=True):
        for seg in self._segments:
            yield seg

    def from_pretrained(self, *args, **kwargs):
        return self
