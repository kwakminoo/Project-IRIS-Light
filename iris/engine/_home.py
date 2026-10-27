"""EngineHome pin and EnginePython probe.

Agent-readable:
- Owns: ENGINE_HERMES_SHA, locating EnginePython, import probe.
- Does not: spawn a sidecar, bind :8642, or import run_agent.
- Talks to: iris.engine.types, a short -c import in the engine interpreter.
- Extend via: install_into(runner=...) when tests inject clone. Default calls
  hermes_install with home=EngineHome (never HermesHome).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from iris.engine.types import EngineError, EngineErrorCode, EngineHome, EnginePython
from iris.system.win_subprocess import no_window_kwargs

# Local checkout SHA from HOW.md. Bump this when the hosted tree moves.
ENGINE_HERMES_SHA = "4787e4d56fc8d9265d4c7d3c0fe5accee86b4078"

_PROBE_IMPORT = "import hermes_cli, aiohttp, mcp, ruamel.yaml, dotenv; print('ok')"

_POLLUTION_ENV_KEYS = (
    "VIRTUAL_ENV",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONEXECUTABLE",
    "PYTHONUSERBASE",
    "UV_PROJECT",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PYTHON_PREFERENCE",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
    "PIP_PYTHON",
)


def engine_python(home: EngineHome) -> EnginePython | None:
    venv = Path(home) / "hermes-agent" / "venv"
    if sys.platform == "win32":
        scripts = venv / "Scripts"
        for name in ("python.exe", "python.cmd", "python"):
            candidate = scripts / name
            if candidate.is_file():
                return EnginePython(candidate)
        return None
    candidate = venv / "bin" / "python"
    if candidate.is_file():
        return EnginePython(candidate)
    return None


def _stripped_probe_env(*, home: EngineHome | None, python: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in _POLLUTION_ENV_KEYS:
        env.pop(key, None)
    if home is not None:
        env["HERMES_HOME"] = str(home)
    venv = python.parent.parent
    if venv.is_dir():
        env["VIRTUAL_ENV"] = str(venv)
        scripts = str(python.parent)
        path = env.get("PATH", "")
        if scripts and not path.lower().startswith(scripts.lower()):
            env["PATH"] = scripts + os.pathsep + path
    return env


def _probe_imports(
    python: Path,
    *,
    home: EngineHome | None = None,
    timeout_sec: float = 25.0,
) -> EngineError | None:
    if not python.is_file():
        return EngineError(EngineErrorCode.NOT_INSTALLED, f"engine python missing: {python}")
    try:
        proc = subprocess.run(
            [str(python), "-c", _PROBE_IMPORT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5.0, timeout_sec),
            check=False,
            env=_stripped_probe_env(home=home, python=python),
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return EngineError(EngineErrorCode.WRONG_PYTHON, f"engine python failed: {exc}")
    err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    if proc.returncode != 0:
        detail = err[:400] if err else f"exit {proc.returncode}"
        return EngineError(EngineErrorCode.WRONG_PYTHON, detail)
    if "ok" not in (proc.stdout or ""):
        return EngineError(
            EngineErrorCode.WRONG_PYTHON,
            f"hermes_cli import 응답 이상: {err[:240]}",
        )
    return None


def probe_engine_python(home: EngineHome) -> EngineError | None:
    try:
        python = engine_python(home)
        if python is None:
            return EngineError(EngineErrorCode.NOT_INSTALLED, "engine python is not installed")
        return _probe_imports(Path(python), home=home)
    except Exception as exc:
        return EngineError(EngineErrorCode.WRONG_PYTHON, str(exc))


def install_into(
    home: EngineHome,
    *,
    clone: object | None = None,
    runner: Callable[..., object] | None = None,
) -> None:
    if probe_engine_python(home) is None:
        return
    dest = Path(home) / "hermes-agent"
    if runner is not None:
        runner(dest, sha=ENGINE_HERMES_SHA, clone=clone)
        return
    from iris.system.hermes_install import install_hermes_with_system_python

    install_hermes_with_system_python(home=Path(home), sha=ENGINE_HERMES_SHA)
