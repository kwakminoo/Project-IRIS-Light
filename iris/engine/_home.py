"""EngineHome pin and EnginePython probe.

Agent-readable:
- Owns: ENGINE_HERMES_SHA, locating EnginePython, import probe.
- Does not: spawn a sidecar, bind :8642, or import run_agent.
- Talks to: iris.engine.types, a short -c import in the engine interpreter.
- Extend via: install_into(runner=...) when tests inject clone. Default calls
  iris_agent_install with home=EngineHome (EngineHome only).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from iris.engine.types import EngineError, EngineErrorCode, EngineHome, EnginePython
from iris.system.win_subprocess import no_window_kwargs

def _engine_pin_sha() -> str:
    from iris.infrastructure.agent_runtime import load_pinned_sha

    return load_pinned_sha()


# Prefer vendor/iris-agent-runtime/PIN. Legacy name kept for serin tests.
ENGINE_HERMES_SHA = _engine_pin_sha()

_PROBE_IMPORT = (
    "import sys\n"
    "from pathlib import Path\n"
    "import iris_agent_cli, run_agent\n"
    "from run_agent import AIAgent\n"
    "import mcp, ruamel.yaml, dotenv\n"
    "root = Path(sys.argv[1]).resolve()\n"
    "assert Path(sys.prefix).resolve() == root / 'venv', 'unexpected engine environment'\n"
    "assert Path(run_agent.__file__).resolve() == root / 'run_agent.py', 'unexpected agent source'\n"
    "assert Path(iris_agent_cli.__file__).resolve().is_relative_to(root), 'unexpected CLI source'\n"
    "print('ok')\n"
)

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
    from iris.infrastructure.agent_runtime import selected_owned_engine

    checkout = selected_owned_engine(Path(home))
    return checkout_python(checkout) if checkout is not None else None


def checkout_python(checkout: Path) -> EnginePython | None:
    venv = checkout / "venv"
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
    env["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
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
            [str(python), "-I", "-c", _PROBE_IMPORT, str(python.parent.parent.parent)],
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
            f"agent CLI import 응답 이상: {err[:240]}",
        )
    return None


def probe_engine_python(home: EngineHome, *, python: EnginePython | None = None) -> EngineError | None:
    try:
        python = python or engine_python(home)
        if python is None:
            return EngineError(EngineErrorCode.NOT_INSTALLED, "No verified Owned engine is available. Run IRIS Setup to recover the engine.")
        return _probe_imports(Path(python), home=home)
    except Exception as exc:
        return EngineError(EngineErrorCode.WRONG_PYTHON, str(exc))


def install_into(
    home: EngineHome,
    *,
    clone: object | None = None,
    runner: Callable[..., object] | None = None,
) -> EngineError | None:
    if probe_engine_python(home) is None:
        return
    from iris.infrastructure.agent_runtime import IRIS_AGENT_CHECKOUT_NAME, read_engine_selection

    # New installs always create under canonical iris-agent.
    dest = Path(home) / IRIS_AGENT_CHECKOUT_NAME
    if runner is not None:
        runner(dest, sha=_engine_pin_sha(), clone=clone)
        return
    from iris.system.iris_agent_install import install_iris_agent_with_system_python, rollback_iris_agent

    if read_engine_selection(Path(home))[1] is not None:
        try:
            rollback_iris_agent(Path(home))
            return None
        except (OSError, RuntimeError, ValueError):
            pass  # No usable recovery slot; materialize the bundled source.

    result = install_iris_agent_with_system_python(
        home=Path(home), sha=_engine_pin_sha()
    )
    if result is not None and not getattr(result, "ok", True):
        return EngineError(
            EngineErrorCode.NOT_INSTALLED,
            str(getattr(result, "message", "Iris Agent 설치에 실패했습니다.")),
        )
