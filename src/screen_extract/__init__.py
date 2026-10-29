"""Extração de respostas de um vídeo de tela compartilhada (100% local).

Fluxo: frames → recorte → descarte de repetidos/borrados → OCR (Tesseract)
com detecção de caixas marcadas → consolidação do último estado por item.
Nada sai da máquina e nenhum frame é gravado fora de uma pasta temporária.
"""
from src.screen_extract.models import Item, Leitura, Linha
from src.screen_extract.pipeline import Extraction, extract

__all__ = ["Extraction", "Item", "Leitura", "Linha", "extract"]
