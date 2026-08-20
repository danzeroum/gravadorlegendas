"""Diagnóstico de áudio Linux (PipeWire / PulseAudio).

Mostra:
- Sistema operacional e sessão atual (X11/Wayland).
- Se PipeWire está disponível e rodando.
- Dispositivos/fontes de áudio detectados via pactl.
- Possíveis monitor sources (áudio do sistema).
- Orientações claras caso nenhuma fonte seja encontrada.

Uso:
    python3 scripts/diagnose_linux_audio.py

Não requer nenhum binding Python — apenas ferramentas CLI do sistema
(pactl, pw-cli, pw-record).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return -1, "", f"{cmd[0]} não encontrado"
    except subprocess.TimeoutExpired:
        return -2, "", f"timeout após {timeout}s"


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _info(msg: str) -> None:
    print(f"    {msg}")


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

def diagnose_os_session() -> None:
    _section("SISTEMA OPERACIONAL E SESSÃO")
    print(f"  sys.platform          = {sys.platform!r}")
    print(f"  XDG_SESSION_TYPE      = {os.environ.get('XDG_SESSION_TYPE', '<não definido>')!r}")
    print(f"  XDG_CURRENT_DESKTOP   = {os.environ.get('XDG_CURRENT_DESKTOP', '<não definido>')!r}")
    print(f"  WAYLAND_DISPLAY       = {os.environ.get('WAYLAND_DISPLAY', '<não definido>')!r}")
    print(f"  DISPLAY               = {os.environ.get('DISPLAY', '<não definido>')!r}")
    print(f"  XDG_RUNTIME_DIR       = {os.environ.get('XDG_RUNTIME_DIR', '<não definido>')!r}")

    if sys.platform.startswith("win"):
        _warn("Plataforma Windows — este diagnóstico é voltado para Linux.")
        return
    if not sys.platform.startswith("linux"):
        _warn(f"Plataforma não-Linux: {sys.platform}")
        return

    xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg == "wayland":
        _ok("Sessão Wayland detectada.")
    elif xdg == "x11":
        _ok("Sessão X11 detectada — compatível com captura mss.")
    else:
        _warn(f"Sessão gráfica não detectada via XDG_SESSION_TYPE ({xdg!r}).")
        if os.environ.get("WAYLAND_DISPLAY"):
            _info("WAYLAND_DISPLAY presente — provavelmente Wayland.")
        elif os.environ.get("DISPLAY"):
            _info("DISPLAY presente — provavelmente X11.")


def diagnose_pipewire() -> None:
    _section("PIPEWIRE")
    if not _have("pw-cli"):
        _fail("pw-cli não encontrado. Instale: sudo dnf install pipewire-utils")
    else:
        _ok("pw-cli encontrado no PATH")
        rc, out, err = _run(["pw-cli", "--version"])
        if rc == 0:
            _info(f"versão: {out.strip() or err.strip()}")
        else:
            _warn(f"não foi possível obter versão: {err.strip()}")

    if not _have("pw-record"):
        _fail("pw-record não encontrado. Instale: sudo dnf install pipewire-utils")
    else:
        _ok("pw-record encontrado no PATH")

    if not _have("pw-cat"):
        _warn("pw-cat não encontrado (opcional, mas recomendado).")

    # Socket PipeWire
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    socket_path = os.path.join(runtime_dir, "pipewire-0") if runtime_dir else ""
    if socket_path and os.path.exists(socket_path):
        _ok(f"Socket PipeWire ativo: {socket_path}")
    else:
        _fail(f"Socket PipeWire não encontrado em {socket_path!r}")
        _info("Verifique se o serviço está rodando:")
        _info("  systemctl --user status pipewire pipewire-pulse")

    # pw-cli info
    if _have("pw-cli") and socket_path and os.path.exists(socket_path):
        rc, out, err = _run(["pw-cli", "info"], timeout=3)
        if rc == 0 and out:
            _info("Saída de `pw-cli info`:")
            for line in out.strip().splitlines()[:6]:
                _info(f"  {line}")
        else:
            _warn(f"pw-cli info falhou: {err.strip()}")


def diagnose_pulseaudio() -> None:
    _section("PULSEAUDIO / PIPEWIRE-PULSE")
    if not _have("pactl"):
        _fail("pactl não encontrado. Instale: sudo dnf install pulseaudio-libs-utils")
        return
    _ok("pactl encontrado no PATH")
    rc, out, err = _run(["pactl", "info"], timeout=3)
    if rc == 0:
        for line in out.strip().splitlines()[:8]:
            _info(line)
    else:
        _fail(f"pactl info falhou: {err.strip()}")
        _info("Se você usa PipeWire, instale pipewire-pulse:")
        _info("  sudo dnf install pipewire-pulseaudio")


def diagnose_sources() -> None:
    _section("FONTES DE ÁUDIO (SOURCES)")
    """Lista microfones e monitores (áudio do sistema)."""
    if not _have("pactl"):
        _fail("pactl não disponível — não é possível listar fontes.")
        return
    rc, out, err = _run(["pactl", "list", "sources"], timeout=8)
    if rc != 0:
        _fail(f"pactl list sources falhou: {err.strip()}")
        return

    # Parser simples — divide por "Source #N"
    blocks = []
    current = []
    current_id = None
    for line in out.splitlines():
        if line.startswith("Source #"):
            if current_id is not None:
                blocks.append((current_id, current))
            current_id = line.split("#", 1)[1].strip()
            current = []
        else:
            current.append(line)
    if current_id is not None:
        blocks.append((current_id, current))

    if not blocks:
        _warn("Nenhuma fonte de áudio encontrada.")
        _info("Possíveis causas:")
        _info("  - PipeWire/PulseAudio não está rodando")
        _info("  - Sem microfone conectado")
        _info("  - Sem sink de saída ativo (logo, sem monitor)")
        return

    monitor_count = 0
    input_count = 0
    for src_id, body in blocks:
        name = ""
        desc = ""
        is_monitor = False
        for line in body:
            stripped = line.strip()
            if stripped.startswith("Name:"):
                name = stripped[5:].strip()
                if ".monitor" in name:
                    is_monitor = True
            elif stripped.startswith("Description:"):
                desc = stripped[12:].strip()
        kind = "MONITOR (áudio do sistema)" if is_monitor else "INPUT (microfone)"
        if is_monitor:
            monitor_count += 1
        else:
            input_count += 1
        print(f"  Source #{src_id}  [{kind}]")
        _info(f"Name:        {name}")
        _info(f"Description: {desc}")
        print()

    _ok(f"Total: {input_count} microfone(s), {monitor_count} monitor(es).")

    if monitor_count == 0:
        _warn("Nenhuma fonte monitor encontrada — captura de áudio do sistema indisponível.")
        _info("Para capturar áudio do sistema, é necessário ter um sink de saída ativo.")
        _info("Tocar qualquer som (música, vídeo) costuma criar o monitor automaticamente.")


def diagnose_sinks() -> None:
    _section("SINKS DE SAÍDA")
    if not _have("pactl"):
        return
    rc, out, err = _run(["pactl", "list", "sinks"], timeout=8)
    if rc != 0:
        _warn(f"pactl list sinks falhou: {err.strip()}")
        return

    blocks = []
    current = []
    current_id = None
    for line in out.splitlines():
        if line.startswith("Sink #"):
            if current_id is not None:
                blocks.append((current_id, current))
            current_id = line.split("#", 1)[1].strip()
            current = []
        else:
            current.append(line)
    if current_id is not None:
        blocks.append((current_id, current))

    if not blocks:
        _warn("Nenhum sink de saída encontrado.")
        return

    for sink_id, body in blocks:
        desc = ""
        for line in body:
            stripped = line.strip()
            if stripped.startswith("Description:"):
                desc = stripped[12:].strip()
        print(f"  Sink #{sink_id}: {desc}")
    _ok(f"Total: {len(blocks)} sink(s).")


def diagnose_permissions() -> None:
    _section("PERMISSÕES")
    uid = os.getuid()
    print(f"  UID: {uid}")
    if uid == 0:
        _warn("Rodando como root — NÃO recomendado para áudio em sessão gráfica.")
        _info("PipeWire roda no espaço do usuário; rode como usuário comum.")

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime_dir:
        try:
            stat = os.stat(runtime_dir)
            print(f"  XDG_RUNTIME_DIR dono: uid={stat.st_uid} (esperado: {uid})")
            if stat.st_uid != uid:
                _fail("XDG_RUNTIME_DIR não pertence ao usuário atual.")
            else:
                _ok("XDG_RUNTIME_DIR pertence ao usuário atual.")
        except OSError as e:
            _fail(f"Erro ao acessar XDG_RUNTIME_DIR: {e}")
    else:
        _fail("XDG_RUNTIME_DIR não definido — ambiente inadequado.")


def diagnose_recommendations() -> None:
    _section("ORIENTAÇÕES")
    print("  Comandos úteis (Fedora):")
    print("    sudo dnf install pipewire pipewire-utils pipewire-pulseaudio")
    print("    systemctl --user status pipewire pipewire-pulse")
    print("    systemctl --user restart pipewire pipewire-pulse")
    print()
    print("  Para capturar áudio do sistema, selecione uma fonte MONITOR")
    print("  na aba Áudio do Gravador de Legendas. Monitores aparecem com")
    print("  prefixo '🔊' quando o backend PipeWire está ativo.")
    print()
    print("  Se nenhuma fonte monitor aparece:")
    print("    1. Verifique se há um sink ativo (tocando som).")
    print("    2. Reinicie o serviço: systemctl --user restart pipewire")
    print("    3. Faça logout/login se o problema persistir.")


def main() -> int:
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Diagnóstico de Áudio Linux — Gravador de Legendas         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    diagnose_os_session()
    diagnose_pipewire()
    diagnose_pulseaudio()
    diagnose_sources()
    diagnose_sinks()
    diagnose_permissions()
    diagnose_recommendations()
    print()
    print("Diagnóstico concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
