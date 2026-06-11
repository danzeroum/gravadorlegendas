import os
import tempfile

from src.storage.file_manager import FileManager


class TestFileManager:
    def test_build_path_includes_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileManager(tmpdir)
            path = fm.build_path("teste")
            assert "teste" in os.path.basename(path)
            assert path.endswith(".txt")

    def test_save_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileManager(tmpdir)
            path = os.path.join(tmpdir, "test.txt")
            fm.save_line(path, "linha 1")
            fm.save_line(path, "linha 2")
            content = fm.read_all(path)
            assert "linha 1" in content
            assert "linha 2" in content

    def test_clean_and_sort(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileManager(tmpdir)
            inp = os.path.join(tmpdir, "input.txt")
            out = os.path.join(tmpdir, "output.txt")
            with open(inp, "w", encoding="utf-8") as f:
                f.write("zeta\nalpha\nbeta\nalpha\n")
            count = fm.clean_and_sort(inp, out)
            assert count == 3
            with open(out, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            assert lines == ["alpha", "beta", "zeta"]

    def test_write_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileManager(tmpdir)
            path = os.path.join(tmpdir, "out.txt")
            fm.write_all(path, "conteudo")
            assert fm.read_all(path) == "conteudo"
