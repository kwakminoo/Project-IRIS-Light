"""Prove sidecar model_tool_names load path needs no PyQt6 / iris.engine package.

Sidecar uses ``_load_local_helper("model_tool_names")`` (file-location). Package
``from iris.engine.model_tool_names`` pulls ``iris.engine.__init__`` → PyQt6 and
fails in the engine venv.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SIDECAR = _HERE / "_sidecar_main.py"
_MODEL_NAMES = _HERE / "model_tool_names.py"
_REPO = _HERE.parent.parent


def _engine_venv_python() -> Path | None:
    candidates = (
        Path.home() / ".iris-light" / "agent" / "iris-agent" / "venv" / "Scripts" / "python.exe",
        Path.home() / ".iris-light" / "agent" / "hermes-agent" / "venv" / "Scripts" / "python.exe",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_model_tool_names_like_sidecar():
    """Same contract as ``_sidecar_main._load_local_helper("model_tool_names")``."""
    module_name = "_iris_sidecar_model_tool_names_check"
    spec = importlib.util.spec_from_file_location(module_name, _MODEL_NAMES)
    if spec is None or spec.loader is None:
        raise ImportError("model_tool_names")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def check_sidecar_scrape() -> None:
    src = _SIDECAR.read_text(encoding="utf-8")
    assert '_load_local_helper("model_tool_names")' in src, (
        "sidecar must load model_tool_names via _load_local_helper"
    )
    assert "from iris.engine.model_tool_names" not in src, (
        "package import of model_tool_names reintroduces PyQt6 chain"
    )
    print("sidecar_scrape ok")


def check_inprocess_file_location_load() -> None:
    before = set(sys.modules)
    mod = _load_model_tool_names_like_sidecar()
    regs = mod.iris_model_registrations("home")
    assert [r[0] for r in regs] == list(mod.iris_backed_model_names())
    added = set(sys.modules) - before
    # File-location load must not pull Qt or the iris.engine package.
    assert not any(n == "PyQt6" or n.startswith("PyQt6.") for n in added), added
    assert "iris.engine" not in added, added
    print("inprocess_file_location_load ok", f"n={len(regs)}")


def check_engine_venv_subprocess() -> None:
    py = _engine_venv_python()
    if py is None:
        print("engine_venv_subprocess skip (no engine venv python)")
        return
    code = r"""
import importlib.util, sys
from pathlib import Path
path = Path(r"%s")
name = "_iris_sidecar_model_tool_names_engine"
spec = importlib.util.spec_from_file_location(name, path)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[name] = mod
spec.loader.exec_module(mod)
regs = mod.iris_model_registrations("home")
assert [r[0] for r in regs] == list(mod.iris_backed_model_names())
assert "write_file" in {r[0] for r in regs}
assert "iris.engine" not in sys.modules
try:
    import PyQt6  # noqa: F401
except ModuleNotFoundError:
    pass
else:
    raise SystemExit("unexpected: PyQt6 present in engine venv")
print("engine_ok", len(regs))
""" % (_MODEL_NAMES.as_posix(),)
    env = dict(os.environ)
    # Repo on path like product sidecar; must still avoid package init for familiar.
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [str(py), "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
    )
    assert proc.returncode == 0, (
        f"engine venv familiar load failed rc={proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert "engine_ok" in proc.stdout, proc.stdout
    print("engine_venv_subprocess ok", proc.stdout.strip())


def main() -> None:
    check_sidecar_scrape()
    check_inprocess_file_location_load()
    check_engine_venv_subprocess()


if __name__ == "__main__":
    main()
