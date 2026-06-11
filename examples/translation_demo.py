"""Demonstração do tradutor MarianMT.

Uso:
    python examples/translation_demo.py
"""
from src.translation.marianmt import TranslatorMarianMT


def main():
    translator = TranslatorMarianMT()
    phrases = [
        "Good morning everyone",
        "The project deadline is next Friday",
        "Can you review this document?",
    ]

    print("Carregando modelo de tradução...\n")
    for phrase in phrases:
        translated = translator.translate(phrase)
        print(f"EN: {phrase}")
        print(f"PT: {translated}")
        print()


if __name__ == "__main__":
    main()
