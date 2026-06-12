"""Download de modelos de áudio do Hugging Face.

Baixa modelos necessários para transcrição (faster-whisper),
VAD (silero-vad) e diarização (pyannote/diart).

Uso:
    python scripts/setup_audio_models.py          # modelos padrão
    python scripts/setup_audio_models.py --all     # todos (inclui large)
    python scripts/setup_audio_models.py --whisper tiny  # específico
"""
import argparse
from pathlib import Path


WHISPER_SIZES = ["tiny", "tiny.en", "base", "base.en", "small", "medium", "large-v3"]
_MODELS_DIR = Path.home() / ".cache" / "gravador" / "audio"


def _ensure_dir():
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return _MODELS_DIR


def download_whisper(size: str = "tiny"):
    """Baixa modelo faster-whisper via CTranslate2."""
    print(f"\n📥 Baixando faster-whisper {size}...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(size, download_root=str(_MODELS_DIR / "whisper"), device="cpu")
        _ = model.model  # força download completo
        print(f"   ✅ faster-whisper {size} pronto em {_MODELS_DIR / 'whisper'}")
    except ImportError:
        print("   ❌ faster-whisper não instalado. pip install faster-whisper")


def download_silero_vad():
    """Baixa modelo Silero VAD."""
    print("\n📥 Baixando silero-vad...")
    try:
        import silero_vad
        _ = silero_vad.load_silero_vad()
        print("   ✅ silero-vad pronto")
    except ImportError:
        print("   ❌ silero-vad não instalado. pip install silero-vad")
    except Exception as e:
        print(f"   ⚠️  Erro ao carregar silero-vad: {e}")


def download_diarization(token: str | None = None):
    """Baixa modelos pyannote/diart (requer aceite de termos no HF)."""
    print("\n📥 Baixando modelos de diarização (pyannote + diart)...")
    print("   ⚠️  Requer aceite dos termos em https://hf.co/pyannote/speaker-diarization-3.1")
    print("   ⚠️  Requer token HF: https://hf.co/settings/tokens")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            "pyannote/speaker-diarization-3.1",
            cache_dir=str(_MODELS_DIR / "diarization"),
            token=token,
        )
        print("   ✅ pyannote/speaker-diarization-3.1 baixado")
    except ImportError:
        print("   ❌ huggingface-hub não instalado")
    except Exception as e:
        print(f"   ⚠️  Erro ao baixar diarização: {e}")
        print("   Você pode ignorar se não for usar diarização.")


def main():
    parser = argparse.ArgumentParser(description="Download de modelos de áudio")
    parser.add_argument("--whisper", default="tiny", choices=WHISPER_SIZES,
                        help="Tamanho do modelo Whisper")
    parser.add_argument("--all", action="store_true", help="Baixa todos os modelos")
    parser.add_argument("--token", default=None, help="Token Hugging Face (para diarização)")
    args = parser.parse_args()

    print(f"📍 Diretório de cache: {_ensure_dir()}")
    print("=" * 50)

    download_whisper("tiny" if not args.all else "base")
    if args.all:
        download_whisper("base")
        download_whisper("small")

    download_silero_vad()

    if args.all or args.token:
        download_diarization(token=args.token)

    print(f"\n✅ Setup concluído. Modelos em: {_MODELS_DIR}")


if __name__ == "__main__":
    main()
