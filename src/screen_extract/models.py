"""Tipos do módulo (sem dependências pesadas)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Linha:
    """Uma linha de texto lida de um frame.

    Attributes:
        texto: Texto da linha.
        x, y, w, h: Caixa da linha no frame recortado, em pixels.
        marcado: True/False se há caixa de seleção à esquerda; None se não há.
    """

    texto: str
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    marcado: bool | None = None


@dataclass
class Leitura:
    """Linhas lidas de um frame, com o instante do vídeo (segundos)."""

    t: float
    linhas: list[Linha] = field(default_factory=list)


@dataclass
class Item:
    """Estado consolidado de uma linha ao longo do vídeo.

    Attributes:
        tipo: ``pergunta`` | ``opcao`` (tem caixa) | ``texto`` (sem caixa).
        pergunta: Pergunta a que o item pertence (vazio na própria pergunta).
        marcado: Último estado visto (None = nunca teve caixa).
        primeira_vez / ultima_vez: Instantes (s) da 1ª e da última aparição.
        vezes_visto: Em quantos frames lidos apareceu.
        mudancas: ``[(t, marcado)]`` a cada troca de estado.
    """

    tipo: str
    texto: str
    pergunta: str = ""
    marcado: bool | None = None
    primeira_vez: float = 0.0
    ultima_vez: float = 0.0
    vezes_visto: int = 0
    mudancas: list[tuple[float, bool | None]] = field(default_factory=list)
