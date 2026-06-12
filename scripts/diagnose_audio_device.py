"""Diagnóstico de dispositivos de áudio WASAPI (loopback).

Lista todos os dispositivos de áudio disponíveis via PyAudio,
destacando entradas WASAPI e loopback. Executar como administrador
para garantir acesso ao loopback.
"""
import sys
import contextlib


def diagnose():
    """Tenta listar dispositivos WASAPI. Falha graciosamente se PyAudio não estiver instalado."""
    try:
        import pyaudio
    except ImportError:
        print("PyAudio não instalado. Execute: pip install PyAudio")
        sys.exit(1)

    pa = pyaudio.PyAudio()
    info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    wasapi_index = info["index"]
    print(f"HOST API WASAPI : index={wasapi_index}  name={info['name']!r}")
    print(f"  Devices : {info['deviceCount']}")
    print()

    dev_count = pa.get_device_count()
    print(f"{'INDEX':<6} {'NAME':<55} {'CH':<4} {'RATE':<8} {'SAMPWIDTH':<10} {'LOOPBACK':<10}")
    print("-" * 105)

    loopback_found = False
    for i in range(dev_count):
        dev = pa.get_device_info_by_index(i)
        if dev["hostApi"] != wasapi_index:
            continue
        is_loopback = dev.get("maxInputChannels", 0) > 0 and "loopback" in dev["name"].lower()
        if is_loopback:
            loopback_found = True
        print(
            f"{i:<6} {dev['name'][:54]:<55} "
            f"{dev.get('maxInputChannels', 0):<4} "
            f"{int(dev.get('defaultSampleRate', 0)):<8} "
            f"{dev.get('sSampleWidth', '?')!s:<10} "
            f"{'✅' if is_loopback else '❌':<10}"
        )

    if not loopback_found:
        print("\n⚠️  Nenhum dispositivo loopback encontrado.")
        print("   No Windows 10+ (1803+) o loopback WASAPI é nativo.")
        print("   Tente executar este script como ADMINISTRADOR.")
    else:
        print("\n✅ Dispositivo(s) loopback encontrado(s). Use o INDEX na configuração.")

    pa.terminate()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        diagnose()
