"""Detecção heurística de perguntas em texto."""


class QuestionDetector:
    """Detecta se um texto é uma pergunta usando heurísticas.

    Verifica se o texto termina com '?' ou começa com
    palavras interrogativas (inglês e português).
    """

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
        """Verifica se o texto é uma pergunta.

        Args:
            text: Texto a ser analisado.

        Returns:
            True se o texto parece ser uma pergunta.
        """
        text = text.strip()
        if not text:
            return False
        if text.endswith("?"):
            return True
        first_word = text.split()[0].lower().rstrip(":,.!;")
        return first_word in self.INTERROGATIVES

    def extract_question(self, text: str) -> str | None:
        """Retorna o texto se for pergunta, None caso contrário.

        Args:
            text: Texto a ser analisado.

        Returns:
            O texto original se for pergunta, None caso contrário.
        """
        if self.is_question(text):
            return text
        return None
