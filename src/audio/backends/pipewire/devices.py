"""Descoberta de dispositivos PipeWire/PulseAudio via pactl.

Por que pactl e não pw-cli?
    - ``pactl list`` funciona em PipeWire-Pulse (default no Fedora) e
      em PulseAudio legado.
    - ``pw-cli list`` expõe nós PipeWire nativos, mas a sintaxe é menos
      estável e nomes de propriedades mudam entre versões.
    - pactl dá ``monitor`` sources explicitamente, que é exatamente o
      que precisamos para captura de áudio do sistema.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

from src.platform.types import AudioDevice

_logger = logging.getLogger(__name__)

# Parser para blocos "Source #N" do `pactl list sources`
_SOURCE_BLOCK_RE = re.compile(
    r"^Source #(?P<id>\d+)\s*$\n^(?P<body>(?:.*\n)*?)(?=^Source #|\Z)",
    re.MULTILINE,
)

_PROP_RE = re.compile(r"^\s*(?P<k>[\w\.\-\s]+?)\s*[:=]\s*(?P<v>.*?)\s*$")


def _have_pactl() -> bool:
    return shutil.which("pactl") is not None


def _pactl_env() -> dict:
    """Força locale C para que `pactl` emita saída em inglês.

    Em desktops com locale pt_BR (ex.: Fedora GNOME em português), o
    `pactl` traduz os cabeçalhos dos blocos ("Fonte #50", "Estado:",
    "Descrição:"), o que quebra o parser que espera keywords estáveis
    em inglês ("Source #", "State:", "Description:"). Forçar
    LC_ALL/LANG=C normaliza a saída independente do locale do usuário.
    """
    env = os.environ.copy()
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        env[var] = "C"
    return env


def _run_pactl_list(kind: str) -> str:
    """Roda ``pactl list <kind>`` (sources | sinks | source-outputs)."""
    if not _have_pactl():
        return ""
    try:
        proc = subprocess.run(
            ["pactl", "list", kind],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            env=_pactl_env(),
        )
        if proc.returncode != 0:
            _logger.warning(
                "pactl list %s falhou (rc=%d): %s",
                kind, proc.returncode, proc.stderr.strip(),
            )
            return ""
        return proc.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _logger.warning("pactl list %s: %s", kind, e)
        return ""


def _parse_devices(text: str, kind: str) -> list[AudioDevice]:
    """Extrai dispositivos de blocos `Source #N` ou `Sink #N`.

    Args:
        text: Saída de ``pactl list <kind>`` (sources | sinks).
        kind: "sources" ou "sinks" — usado apenas para distinguir monitor
            de input/output.
    """
    devices: list[AudioDevice] = []
    if not text:
        return devices

    # ``pactl`` emite blocos iniciados por "Source #N" ou "Sink #N"
    # (singular, sem "s" final). kind pode ser "sources" ou "sinks".
    block_keyword = kind[:-1] if kind.endswith("s") else kind  # "Source" / "Sink"
    block_keyword_cap = block_keyword.capitalize()

    blocks = re.findall(
        r"^" + block_keyword_cap + r" #(\d+)\s*\n(.*?)(?=^" + block_keyword_cap + r" #|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    for dev_id, body in blocks:
        props: dict[str, str] = {}
        for line in body.splitlines():
            m = _PROP_RE.match(line)
            if m:
                props[m.group("k")] = m.group("v").strip()

        name = props.get("Description") or props.get("Name") or f"device-{dev_id}"
        # Samples format: "sample_spec: s16le 2ch 44100Hz"
        sample_spec = props.get("Sample Specification", "") or props.get(
            "sample_spec", ""
        )
        channels = 1
        rate = 16000
        m_ch = re.search(r"(\d+)ch", sample_spec)
        m_rate = re.search(r"(\d+)Hz", sample_spec)
        if m_ch:
            channels = int(m_ch.group(1))
        if m_rate:
            rate = int(m_rate.group(1))

        state = props.get("State", "").lower()
        is_monitor = "monitor" in name.lower() or ".monitor" in props.get("Name", "")
        if kind == "sources":
            audio_kind = "monitor" if is_monitor else "input"
        else:
            audio_kind = "output"

        devices.append(
            AudioDevice(
                id=str(dev_id),
                name=name.strip(),
                kind=audio_kind,
                channels=channels,
                sample_rate=rate,
                is_default=(state == "running"),
                backend="pipewire",
            )
        )
    return devices


def list_pipewire_devices() -> list[AudioDevice]:
    """Lista fontes (microfones + monitores) e sinks via pactl.

    Returns:
        Lista vazia se pactl não estiver disponível ou o servidor
        PipeWire/PulseAudio não responder.
    """
    if not _have_pactl():
        _logger.warning(
            "pactl não encontrado. Instale pipewire-utils ou pulseaudio-utils."
        )
        return []

    sources = _parse_devices(_run_pactl_list("sources"), "sources")
    # Sinks são úteis para o usuário identificar qual saída ele quer
    # monitorar; o monitor correspondente aparece em sources com nome
    # "<sink-name>.monitor".
    sinks = _parse_devices(_run_pactl_list("sinks"), "sinks")

    # Marcar monitores com nome amigável
    sink_names = {s.name: s for s in sinks}
    out: list[AudioDevice] = []
    for src in sources:
        if src.kind == "monitor":
            # Tentar casar com sink correspondente para nome amigável
            for sink_name, sink in sink_names.items():
                if sink_name and sink_name.lower() in src.name.lower():
                    src = AudioDevice(
                        id=src.id,
                        name=f"Áudio do Sistema ({sink.name})",
                        kind="monitor",
                        channels=src.channels,
                        sample_rate=src.sample_rate,
                        is_default=src.is_default,
                        backend="pipewire",
                    )
                    break
            else:
                src = AudioDevice(
                    id=src.id,
                    name=f"Áudio do Sistema ({src.name})",
                    kind="monitor",
                    channels=src.channels,
                    sample_rate=src.sample_rate,
                    is_default=src.is_default,
                    backend="pipewire",
                )
        out.append(src)
    return out
