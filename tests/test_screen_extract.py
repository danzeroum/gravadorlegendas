"""Extração de respostas de tela compartilhada (src/screen_extract)."""
import csv
import shutil

import numpy as np
import pytest
from PIL import Image

from scripts import extrair_tela
from src.screen_extract.checkbox import detect_checkbox
from src.screen_extract.consolidate import consolidate, is_question, norm
from src.screen_extract.crop import Region, RegionError, crop, parse_region
from src.screen_extract.dedupe import changed_fraction, is_blurry, sharpness, signature
from src.screen_extract.export import save_all, to_csv
from src.screen_extract.models import Leitura, Linha
from src.screen_extract.pipeline import extract
from tests.screen_fixtures import FACE_BAND, H, W, draw_form, write_video

pytest.importorskip("av")


# --- recorte -----------------------------------------------------------

def test_parse_region_pixels_and_percent():
    assert parse_region("10,20,300,400") == Region(10, 20, 300, 400, False)
    r = parse_region("10%,0%,50%,100%")
    assert r.relative and r.to_box(200, 100) == (20, 0, 120, 100)


@pytest.mark.parametrize("bad", ["1,2,3", "a,b,c,d", "10%,2,3,4"])
def test_parse_region_invalid(bad):
    with pytest.raises(RegionError):
        parse_region(bad)


def test_region_outside_frame_rejected():
    with pytest.raises(RegionError):
        Region(0, 0, 900, 100).to_box(800, 450)


def test_crop_removes_face_band():
    img = draw_form("1. Pergunta?", [("Sim", False)])
    out = crop(img, Region(0, 0, W - FACE_BAND, H))
    assert out.size == (W - FACE_BAND, H)
    assert not (np.asarray(out) == (120, 90, 70)).all(axis=-1).any()


# --- dedupe ------------------------------------------------------------

def test_dedupe_detects_checkbox_tick_but_not_noise():
    a = draw_form("1. P?", [("Sim", False), ("Não", False)])
    b = draw_form("1. P?", [("Sim", False), ("Não", True)])
    sa, sb = signature(a), signature(b)
    assert changed_fraction(sa, signature(a)) == 0
    assert changed_fraction(sa, sb) >= 0.0005
    noisy = np.asarray(a, dtype=np.int16) + np.random.default_rng(0).integers(-5, 6, (H, W, 3))
    noisy = Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))
    assert changed_fraction(sa, signature(noisy)) < 0.0005


def test_blur_lowers_sharpness():
    from PIL import ImageFilter
    img = draw_form("1. P?", [("Sim", False)])
    assert is_blurry(sharpness(img.filter(ImageFilter.GaussianBlur(6))), sharpness(img), 0.5)
    assert not is_blurry(sharpness(img), sharpness(img), 0.5)


# --- caixa marcada -----------------------------------------------------

@pytest.mark.parametrize("marked", [True, False])
def test_detect_checkbox(marked):
    img = draw_form("x", [("Opção", marked)]).convert("L")
    gray = np.asarray(img)
    # texto "Opção" começa em x=80, y=100, altura ~22
    assert detect_checkbox(gray, 80, 100, 90, 22) is marked


def test_detect_checkbox_none_without_box():
    gray = np.full((100, 300), 255, np.uint8)
    assert detect_checkbox(gray, 100, 40, 80, 20) is None


# --- consolidação ------------------------------------------------------

def L(texto, marcado=None):
    return Linha(texto, marcado=marcado)


def test_is_question():
    assert is_question(L("Há compartilhamento?"))
    assert is_question(L("1.2 Base legal"))
    assert not is_question(L("Sim", marcado=False))


def test_consolidate_keeps_last_state_and_history():
    q = "1.1 Compartilha dados?"
    leituras = [
        Leitura(0, [L(q), L("Sim", False), L("Não", False)]),
        Leitura(4, [L(q), L("Sim", True), L("Não", False)]),
        Leitura(8, [L(q), L("Sim", False), L("Não", True)]),
    ]
    items = {i.texto: i for i in consolidate(leituras)}
    assert items["Sim"].marcado is False and items["Não"].marcado is True
    assert items["Sim"].mudancas == [(0, False), (4, True), (8, False)]
    assert items["Sim"].primeira_vez == 0 and items["Sim"].ultima_vez == 8
    assert items["Sim"].pergunta == q


def test_consolidate_merges_ocr_variants_and_carries_question_across_scroll():
    leituras = [
        Leitura(0, [L("2. Qual a base legal?"), L("Consentimento", False)]),
        Leitura(2, [L("Consentimento", True), L("Legítimo interesse", False)]),
        Leitura(4, [L("2. Qual a base legal"), L("Consentlmento", True)]),
    ]
    items = consolidate(leituras)
    assert [i.tipo for i in items].count("pergunta") == 1
    cons = next(i for i in items if i.texto == "Consentimento")
    assert cons.vezes_visto == 3 and cons.marcado is True
    assert next(i for i in items if i.texto == "Legítimo interesse").pergunta.startswith("2.")


def test_norm_ignores_accents_and_case():
    assert norm("  NÃO   se aplica! ") == "nao se aplica"


# --- exportação --------------------------------------------------------

def test_csv_blocks_formula_injection(tmp_path):
    items = consolidate([Leitura(0, [L("=HYPERLINK(1)", True)])])
    path = tmp_path / "a.csv"
    to_csv(items, path)
    rows = list(csv.reader(open(path, encoding="utf-8-sig"), delimiter=";"))
    assert rows[1][2] == "'=HYPERLINK(1)"


# --- pipeline e CLI ----------------------------------------------------

class FakeReader:
    """Lê o 'estado' da tela pela cor do pixel da caixa (sem Tesseract)."""

    def __init__(self):
        self.calls = 0

    def read(self, img):
        self.calls += 1
        marcado = img.convert("L").getpixel((52, 112)) < 120
        return [Linha("1. Pergunta?"), Linha("Não", marcado=marcado)]


@pytest.fixture
def video(tmp_path):
    q = "1. Pergunta?"
    off = draw_form(q, [("Não", False)])
    on = draw_form(q, [("Não", True)])
    return write_video(tmp_path / "reuniao.mp4",
                       [(off, 4), (on, 4), (on, 2)], blur_scenes=None)


def test_extract_skips_repeated_frames(video):
    reader = FakeReader()
    res = extract(video, Region(0, 0, W - FACE_BAND, H), reader, interval_s=1.0)
    assert res.sampled >= 8
    assert res.kept == 2 == reader.calls          # só o início e a marcação
    nao = next(i for i in res.items if i.texto == "Não")
    assert nao.marcado is True and len(nao.mudancas) == 2


def test_extract_rejects_audio_only(tmp_path):
    from src.screen_extract.frames import VideoDecodeError
    from tests.media_fixtures import write_tone
    wav = write_tone(tmp_path / "a.mp3", "libmp3lame")
    with pytest.raises(VideoDecodeError):
        extract(wav, Region(0, 0, 10, 10), FakeReader())


def test_save_all_writes_three_files(video, tmp_path):
    res = extract(video, Region(0, 0, 600, H), FakeReader(), interval_s=2.0)
    paths = save_all(res.items, tmp_path / "out", "reuniao", "reuniao.mp4", {})
    assert {p.suffix for p in paths.values()} == {".json", ".csv", ".md"}
    assert "[x] Não" in paths["md"].read_text(encoding="utf-8")


def test_cli_requires_region(video, capsys, monkeypatch):
    monkeypatch.setattr(extrair_tela, "check_environment", lambda: [])
    monkeypatch.setattr("src.screen_extract.reader.TesseractReader.__init__",
                        lambda self, *a, **k: None)
    code = extrair_tela.main([str(video), "--saida", "/nonexistent"])
    assert code == extrair_tela.EXIT_REGION
    assert "--regiao" in capsys.readouterr().err


def test_cli_calibrate_saves_frame(video, tmp_path):
    out = tmp_path / "cal"
    assert extrair_tela.main([str(video), "--calibrar", "--regiao", "0,0,600,450",
                              "--saida", str(out)]) == 0
    assert (out / "reuniao_calibrar.png").is_file()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract ausente")
def test_end_to_end_with_tesseract(tmp_path):
    pytest.importorskip("pytesseract")
    from src.screen_extract.reader import ReaderError, TesseractReader
    try:
        reader = TesseractReader(lang="eng")
    except ReaderError:
        pytest.skip("idioma eng ausente")
    q = "1.1 Is data shared with third parties?"
    video = write_video(tmp_path / "t.mp4", [
        (draw_form(q, [("Yes", False), ("No", False)]), 4),
        (draw_form(q, [("Yes", False), ("No", True)]), 4),
    ])
    res = extract(video, Region(0, 0, W - FACE_BAND, H), reader, interval_s=2.0)
    by = {i.texto.lower(): i for i in res.items}
    assert by["no"].marcado is True and by["yes"].marcado is False
