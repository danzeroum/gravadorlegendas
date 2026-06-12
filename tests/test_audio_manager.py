from src.audio.manager import AudioManager


class TestAudioManagerMatchSpeaker:
    def setup_method(self):
        self.mgr = AudioManager()
        self.mgr._speaker_segments.append(
            {"speaker": "speaker_0", "start": 0.0, "end": 5.0}
        )
        self.mgr._speaker_segments.append(
            {"speaker": "speaker_1", "start": 6.0, "end": 10.0}
        )

    def test_match_exact(self):
        result = self.mgr._match_speaker(1.0, 4.0)
        assert result == "speaker_0"

    def test_match_second_speaker(self):
        result = self.mgr._match_speaker(7.0, 9.0)
        assert result == "speaker_1"

    def test_no_match_gap(self):
        result = self.mgr._match_speaker(5.1, 5.9)
        assert result is None

    def test_match_within_tolerance(self):
        result = self.mgr._match_speaker(5.2, 5.5)
        assert result is None

    def test_match_spanning_segments(self):
        result = self.mgr._match_speaker(4.0, 7.0)
        assert result == "speaker_0"

    def test_empty_segments_returns_none(self):
        mgr = AudioManager()
        assert mgr._match_speaker(0, 5) is None

    def test_partial_overlap_at_end(self):
        result = self.mgr._match_speaker(3.0, 6.5)
        assert result == "speaker_0"

    def test_match_on_boundary_no_tolerance(self):
        result = self.mgr._match_speaker(5.31, 5.7)
        assert result is None
