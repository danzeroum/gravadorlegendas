"""Gerenciamento de persistência em arquivos .txt."""
import os
from datetime import datetime

from src.config import settings


class FileManager:
    """Gerencia leitura e escrita de arquivos de legenda.

    Cria diretórios automaticamente, gera nomes com timestamp
    e oferece operações de limpeza e ordenação.
    """

    def __init__(self, directory: str | None = None):
        """Inicializa com o diretório de gravação.

        Args:
            directory: Diretório para salvar os arquivos.
                Se None, usa o valor das settings.
        """
        self._directory = directory or settings.recording_dir
        os.makedirs(self._directory, exist_ok=True)

    def build_path(self, prefix: str, suffix: str = "") -> str:
        """Gera um caminho de arquivo com timestamp.

        Formato: {prefix}_{YYYY-MM-DD_HH-MM-SS}{suffix}.txt

        Args:
            prefix: Prefixo do nome do arquivo.
            suffix: Sufixo opcional (ex.: '_resumo').

        Returns:
            Caminho completo do arquivo.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{prefix}_{timestamp}{suffix}.txt"
        return os.path.join(self._directory, filename)

    def save_line(self, path: str, line: str) -> None:
        """Adiciona uma linha ao final do arquivo.

        Args:
            path: Caminho do arquivo.
            line: Linha de texto a adicionar.
        """
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self, path: str) -> str:
        """Lê o conteúdo completo de um arquivo.

        Args:
            path: Caminho do arquivo.

        Returns:
            Conteúdo do arquivo como string.
        """
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_all(self, path: str, content: str) -> None:
        """Escreve conteúdo completo em um arquivo (sobrescreve).

        Args:
            path: Caminho do arquivo.
            content: Conteúdo a escrever.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def clean_and_sort(self, input_path: str, output_path: str) -> int:
        """Remove duplicatas e ordena linhas de um arquivo.

        Args:
            input_path: Caminho do arquivo de entrada.
            output_path: Caminho do arquivo de saída.

        Returns:
            Número de linhas únicas após limpeza.
        """
        with open(input_path, "r", encoding="utf-8") as f:
            words = {line.strip().lower() for line in f if line.strip()}
        sorted_words = sorted(words)
        with open(output_path, "w", encoding="utf-8") as f:
            for w in sorted_words:
                f.write(w + "\n")
        return len(sorted_words)
