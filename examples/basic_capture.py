"""Demonstração básica: captura uma região da tela e exibe o texto extraído.

Uso:
    python examples/basic_capture.py
"""
from src.capture.screen_capture import ScreenCapture
from src.ocr.engine import OCREngine


def main():
    region = {"top": 0, "left": 50, "width": 1820, "height": 80}
    capture = ScreenCapture(region)
    ocr = OCREngine()

    print("Capturando tela...")
    img = capture.capture()
    img = capture.preprocess(img)
    text = ocr.extract_text(img, lang="eng")

    if text:
        print(f"Texto extraído:\n{text}")
    else:
        print("Nenhum texto encontrado na região.")


if __name__ == "__main__":
    main()
