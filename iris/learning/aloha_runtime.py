"""Aloha Act 관리형 runtime (별도 venv) — PyQt6와 PySide6 분리."""

from __future__ import annotations

import logging
import subprocess
import sys
import venv
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("iris.learning.aloha_runtime")

_REQ_PACKAGES = (
    "flask>=2.0",
    "pyautogui==0.9.54",
    "openai",
    "anthropic>=0.37.1",
    "Pillow",
    "numpy",
    "opencv-python-headless>=4.8.0",
    "screeninfo",
    "jsonschema",
    "requests",
    "PySide6",
    "pynput>=1.7.7",
)


def default_runtime_root() -> Path:
    return Path.home() / ".iris-light" / "runtimes" / "aloha"


def runtime_python(root: Path | None = None) -> Path:
    r = root or default_runtime_root()
    if sys.platform == "win32":
        return r / "Scripts" / "python.exe"
    return r / "bin" / "python"


def runtime_status(root: Path | None = None) -> dict:
    r = root or default_runtime_root()
    py = runtime_python(r)
    ok = py.is_file()
    detail = "ready" if ok else "missing"
    if ok:
        try:
            from iris.system.win_subprocess import no_window_kwargs

            proc = subprocess.run(
                [
                    str(py),
                    "-c",
                    (
                        "import importlib.util, sys; "
                        "mods=('PySide6','flask','pyautogui','pynput'); "
                        "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
                        "print('missing dependencies: '+', '.join(missing) if missing else 'ready'); "
                        "sys.exit(1 if missing else 0)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                **no_window_kwargs(),
            )
            if proc.returncode != 0:
                ok = False
                detail = (proc.stdout or proc.stderr or "import failed")[:200]
            else:
                detail = "ready"
        except Exception as exc:
            ok = False
            detail = str(exc)[:200]
    return {
        "root": str(r),
        "python": str(py),
        "ok": ok,
        "detail": detail,
    }


def bootstrap_runtime(
    root: Path | None = None,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """venv 생성 + Act 의존성 설치. IRIS venv는 건드리지 않음."""
    r = root or default_runtime_root()
    r.mkdir(parents=True, exist_ok=True)
    py = runtime_python(r)

    def _prog(msg: str) -> None:
        log.info(msg)
        if progress:
            progress(msg)

    if not py.is_file():
        _prog(f"Creating venv at {r}")
        venv.EnvBuilder(with_pip=True).create(str(r))
    if not py.is_file():
        raise RuntimeError(f"venv python missing: {py}")

    _prog("Upgrading pip")
    from iris.system.win_subprocess import no_window_kwargs

    kw = no_window_kwargs()
    subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip"],
        check=False,
        capture_output=True,
        **kw,
    )
    _prog("Installing Aloha Act packages (incl. PySide6)")
    req_file = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "showui-aloha"
        / "requirements-act-runtime.txt"
    )
    cmd = [str(py), "-m", "pip", "install"]
    if req_file.is_file():
        cmd += ["-r", str(req_file), "PySide6", "pynput>=1.7.7"]
    else:
        cmd += list(_REQ_PACKAGES)
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "pip failed")[:800])
    st = runtime_status(r)
    if not st["ok"]:
        raise RuntimeError(st["detail"])
    _prog("Aloha runtime ready")
    return st


def main() -> int:
    """CLI: python -m iris.learning.aloha_runtime"""
    import argparse

    p = argparse.ArgumentParser(description="Bootstrap Aloha Act managed runtime")
    p.add_argument("--status", action="store_true")
    p.add_argument("--bootstrap", action="store_true")
    args = p.parse_args()
    if args.status or not args.bootstrap:
        print(runtime_status())
        if not args.bootstrap:
            return 0
    try:
        st = bootstrap_runtime(progress=print)
        print(st)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
