from src.nlp.question_detector import QuestionDetector


class TestQuestionDetector:
    def setup_method(self):
        self.detector = QuestionDetector()

    def test_empty_text_not_question(self):
        assert self.detector.is_question("") is False

    def test_question_mark(self):
        assert self.detector.is_question("Is this working?") is True

    def test_question_mark_portuguese(self):
        assert self.detector.is_question("Isso funciona?") is True

    def test_wh_word_start(self):
        assert self.detector.is_question("What is this") is True

    def test_wh_word_portuguese(self):
        assert self.detector.is_question("Como funciona") is True

    def test_statement_not_question(self):
        assert self.detector.is_question("This is a statement") is False

    def test_punctuation_after_first_word(self):
        assert self.detector.is_question("How, exactly, does this work") is True

    def test_extract_question_returns_none_for_statement(self):
        assert self.detector.extract_question("Just a statement") is None

    def test_extract_question_returns_text(self):
        assert self.detector.extract_question("What is this?") == "What is this?"
