"""Rerunnable live checks for PLAYBOOK unit 7. Not imported by IRIS."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

ENGINE_HOME = Path.home() / ".iris-light" / "engine"
DESKTOP_LNK = Path.home() / "Desktop" / "IRIS.lnk"
DIST_EXE = Path(__file__).resolve().parents[2] / "dist" / "IRIS.exe"


def _shortcut_target() -> str:
    script = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{DESKTOP_LNK}");'
        "$s.TargetPath"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def _listen_8642() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return [{"error": str(exc)}]
    for line in (proc.stdout or "").splitlines():
        if ":8642" not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        pid = parts[-1] if parts else ""
        rows.append({"line": line.strip(), "pid": pid})
    return rows


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _engine_probe() -> dict[str, object]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from iris.engine._home import engine_python, probe_engine_python
    from iris.engine.types import EngineHome

    home = EngineHome(ENGINE_HOME)
    python = engine_python(home)
    err = probe_engine_python(home)
    return {
        "home_exists": ENGINE_HOME.is_dir(),
        "lock": (ENGINE_HOME / "iris-hermes-install.lock").is_file(),
        "hermes_agent": (ENGINE_HOME / "hermes-agent").is_dir(),
        "engine_python": str(python) if python else None,
        "probe_ok": err is None,
        "probe_detail": None if err is None else f"{err.code.name}: {err.detail[:200]}",
    }


def main() -> int:
    target = _shortcut_target()
    report = {
        "shortcut_target": target,
        "shortcut_ok": Path(target).resolve() == DIST_EXE.resolve() if target else False,
        "listen_8642": _listen_8642(),
        "ollama_11434": _tcp_open("127.0.0.1", 11434),
        "engine": _engine_probe(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
