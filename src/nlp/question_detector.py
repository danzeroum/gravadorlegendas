class QuestionDetector:
    INTERROGATIVES = {
        "who", "what", "where", "when", "why", "how",
        "is", "are", "am", "was", "were",
        "do", "does", "did",
        "can", "could", "will", "would", "should", "shall", "may", "might",
        "has", "have", "had",
        "que", "qual", "quais", "quem", "como", "onde", "quando",
        "porque", "por que", "quanto",
    }

    def is_question(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if text.endswith("?"):
            return True
        first_word = text.split()[0].lower().rstrip(":,.!;")
        return first_word in self.INTERROGATIVES

    def extract_question(self, text: str) -> str | None:
        if self.is_question(text):
            return text
        return None
