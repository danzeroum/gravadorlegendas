"""Extrai as respostas mostradas numa tela compartilhada (vídeo) — 100% local.

Pensado para gravações de reunião em que a tela mostra um formulário (ex.:
assessment do OneTrust). Lê o vídeo, descarta frames repetidos/borrados, faz
OCR (Tesseract) e detecta caixas marcadas; guarda o último estado de cada item.

    python scripts/extrair_tela.py XPTO --calibrar            # salva um frame p/ ajustar a região
    python scripts/extrair_tela.py XPTO --regiao 5%,8%,70%,85%
    python scripts/extrair_tela.py XPTO --regiao 100,80,1400,900 --intervalo 1
    python scripts/extrair_tela.py --verificar

O vídeo é achado como em ``transcrever_audio.py`` (pasta ``audios/``).
Saída em ``audios/transcricoes/<nome>_tela.{json,csv,md}``. Nada sai da
máquina; frames só existem numa pasta temporária apagada ao final.

Códigos de saída: 0 ok · 2 ambiente incompleto · 3 nome ambíguo ·
4 vídeo não encontrado · 5 arquivo ilegível · 7 região inválida.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.transcrever_audio import (  # noqa: E402
    EXIT_DECODE, EXIT_ENV, OUTPUT_DIR, UserError, _rel, find_audio,
)

EXIT_REGION = 7


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("nome", nargs="?", help="nome (ou caminho) do vídeo")
    p.add_argument("--regiao", help="área da tela compartilhada: x,y,larg,alt em pixels "
                   "ou percentuais (ex.: 5%%,8%%,70%%,85%%)")
    p.add_argument("--calibrar", action="store_true",
                   help="salva um frame com a região desenhada e sai")
    p.add_argument("--em", type=float, default=5.0,
                   help="instante (s) do frame de calibração (padrão 5)")
    p.add_argument("--intervalo", type=float, default=2.0,
                   help="segundos entre frames amostrados (padrão 2)")
    p.add_argument("--limiar", type=float, default=0.05,
                   help="%% de pixels que precisam mudar para o frame contar (padrão 0.05)")
    p.add_argument("--borrado", type=float, default=0.5,
                   help="descarta frames com nitidez < fração×mediana (padrão 0.5; 0 desliga)")
    p.add_argument("--idioma", default="por", help="idioma do Tesseract (padrão por)")
    p.add_argument("--saida", help="pasta de saída (padrão audios/transcricoes)")
    p.add_argument("--verificar", action="store_true", help="checa o ambiente e sai")
    return p


def check_environment() -> list[str]:
    """Lista o que falta (vazia = tudo pronto)."""
    problems = []
    for mod, pip in (("av", "av"), ("PIL", "Pillow"), ("numpy", "numpy"),
                     ("pytesseract", "pytesseract")):
        try:
            __import__(mod)
        except ImportError:
            problems.append(f"módulo Python '{mod}' ausente (pip install {pip})")
    return problems


def calibrate(video: Path, region_text: str | None, at: float, out_dir: Path) -> Path:
    """Salva o frame em ``at`` s; com região, desenha o retângulo. (Contém rostos:
    fica em ``audios/``, fora do git.)"""
    from PIL import ImageDraw

    from src.screen_extract.crop import parse_region
    from src.screen_extract.frames import _frame_at

    import av
    with av.open(str(video)) as c:
        stream = next((s for s in c.streams if s.type == "video"), None)
        if stream is None:
            raise UserError("O arquivo não tem faixa de vídeo.", EXIT_DECODE)
        frame = _frame_at(c, stream, at)
        if frame is None:
            raise UserError(f"O vídeo termina antes de {at:.0f}s; use --em menor.", EXIT_DECODE)
        img = frame.to_image().convert("RGB")
    if region_text:
        box = parse_region(region_text).to_box(*img.size)
        ImageDraw.Draw(img).rectangle(box, outline=(255, 0, 0), width=4)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{video.stem}_calibrar.png"
    img.save(path)
    print(f"Frame de {img.width}x{img.height} salvo em {_rel(path)}")
    return path


def run(args: argparse.Namespace) -> int:
    from src.screen_extract.crop import RegionError, parse_region
    from src.screen_extract.export import save_all
    from src.screen_extract.frames import VideoDecodeError
    from src.screen_extract.pipeline import extract
    from src.screen_extract.reader import ReaderError, TesseractReader

    out_dir = Path(args.saida) if args.saida else OUTPUT_DIR
    video = find_audio(args.nome)
    print(f"Vídeo: {_rel(video)}")

    try:
        if args.calibrar:
            calibrate(video, args.regiao, args.em, out_dir)
            print("Ajuste --regiao e rode de novo; sem --calibrar para extrair.")
            return 0
        if not args.regiao:
            raise UserError("Informe --regiao (recorte da tela compartilhada; "
                            "tira os rostos da análise). Use --calibrar para achá-la.",
                            EXIT_REGION)
        region = parse_region(args.regiao)
        reader = TesseractReader(lang=args.idioma)

        last = [-1]

        def on_progress(f: float, stage: str) -> None:
            pct = int(f * 100) // 10 * 10
            if pct != last[0]:
                last[0] = pct
                print(f"  {pct:3d}%  {stage}", flush=True)

        res = extract(video, region, reader, interval_s=args.intervalo,
                      change_threshold=args.limiar / 100, blur_ratio=args.borrado,
                      on_progress=on_progress)
    except RegionError as e:
        raise UserError(str(e), EXIT_REGION) from e
    except ReaderError as e:
        raise UserError(str(e), EXIT_ENV) from e
    except VideoDecodeError as e:
        raise UserError(str(e), EXIT_DECODE) from e

    meta = {"regiao": args.regiao, "intervalo_s": args.intervalo,
            "duracao_s": round(res.duration_s, 1) if res.duration_s else None,
            "frames_analisados": res.sampled, "frames_mantidos": res.kept,
            "frames_borrados": res.blurry}
    paths = save_all(res.items, out_dir, video.stem, video.name, meta)

    perguntas = sum(i.tipo == "pergunta" for i in res.items)
    marcados = sum(i.marcado is True for i in res.items)
    print("\n=== RESULTADO ===")
    print(f"frames: {res.sampled} analisados, {res.kept} lidos "
          f"({res.blurry} borrados descartados)")
    print(f"itens: {len(res.items)} ({perguntas} perguntas, {marcados} marcados)")
    for ext, p in paths.items():
        print(f"{ext}: {_rel(p)}")
    if not res.items:
        print("Nenhum texto lido: confira a região com --calibrar.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problems = check_environment()
    if args.verificar:
        if problems:
            print("\n".join(f"❌ {p}" for p in problems))
            return EXIT_ENV
        try:
            from src.screen_extract.reader import ReaderError, TesseractReader
            TesseractReader(lang=args.idioma)
        except ReaderError as e:
            print(f"❌ {e}")
            return EXIT_ENV
        print("✅ Tudo pronto: PyAV, Pillow, numpy e Tesseract.")
        return 0
    if problems:
        print("Ambiente incompleto:\n" + "\n".join(f"  - {p}" for p in problems)
              + "\nRode: bash scripts/setup_ambiente.sh")
        return EXIT_ENV
    if not args.nome:
        build_parser().error("informe o nome do vídeo (ou use --verificar).")
    try:
        return run(args)
    except UserError as e:
        print(str(e), file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
