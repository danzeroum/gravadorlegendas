class TestDiarizationProcess:
    def test_diarize_file_returns_empty_on_import_error(self, monkeypatch):
        monkeypatch.setattr("src.audio.diarize.diart", None, raising=False)
        import importlib
        importlib.reload(__import__("src.audio.diarize"))
        from src.audio.diarize import DiarizationProcess
        import multiprocessing
        dp = DiarizationProcess(
            multiprocessing.Queue(), multiprocessing.Queue()
        )
        result = dp.diarize_file("fake.wav")
        assert result == []

    def test_diarize_file_returns_empty_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            "src.audio.diarize.DiarizationProcess._load_pipeline",
            lambda self: False,
        )
        from src.audio.diarize import DiarizationProcess
        import multiprocessing
        dp = DiarizationProcess(
            multiprocessing.Queue(), multiprocessing.Queue()
        )
        result = dp.diarize_file("fake.wav")
        assert result == []

    def test_stop_sets_event(self):
        from src.audio.diarize import DiarizationProcess
        import multiprocessing
        dp = DiarizationProcess(
            multiprocessing.Queue(), multiprocessing.Queue()
        )
        dp.stop()
        assert dp._stop_event.is_set()
