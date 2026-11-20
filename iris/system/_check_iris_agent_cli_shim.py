"""F2 — install overlay plants iris_agent_cli / iris_cli shims over hermes_cli.

F3 supersedes when real iris_agent_cli exists (reverse hermes_cli shim).
Probe names are iris_agent_cli / iris_cli only (no hermes_cli).

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_cli_shim
"""

from __future__ import annotations

import importlib
import inspect
import sys
import tempfile
from pathlib import Path

from iris.infrastructure import agent_runtime as runtime
from iris.system.iris_agent_cli_shim_overlay import apply_iris_agent_cli_shim_overlay


def _check_overlay_makes_iris_cli_importable() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        hermes = root / "hermes_cli"
        hermes.mkdir()
        (hermes / "__init__.py").write_text(
            '"""fake hermes_cli for shim check."""\nMARKER = "hermes"\n',
            encoding="utf-8",
        )
        (hermes / "main.py").write_text(
            "def main():\n    return 0\n",
            encoding="utf-8",
        )
        msgs = apply_iris_agent_cli_shim_overlay(root)
        assert msgs, "overlay should return status"
        assert any("cli shim" in m for m in msgs)

        assert (root / "iris_agent_cli" / "__init__.py").is_file()
        assert (root / "iris_cli" / "__init__.py").is_file()
        assert (root / "iris_agent_cli" / "main.py").is_file()
        assert (root / "iris_cli" / "main.py").is_file()

        sys.path.insert(0, str(root))
        try:
            for name in ("iris_agent_cli", "iris_cli"):
                if name in sys.modules:
                    del sys.modules[name]
                mod = importlib.import_module(name)
                assert getattr(mod, "MARKER", None) == "hermes"
        finally:
            sys.path.remove(str(root))
            for name in ("iris_agent_cli", "iris_cli", "hermes_cli"):
                sys.modules.pop(name, None)

        again = apply_iris_agent_cli_shim_overlay(root)
        assert any("already present" in m for m in again)


def _check_skip_without_agent_cli() -> None:
    with tempfile.TemporaryDirectory() as td:
        msgs = apply_iris_agent_cli_shim_overlay(Path(td))
        assert msgs
        assert any("missing" in m.lower() or "skipped" in m.lower() for m in msgs)


def _check_baseline_wires_cli_shim() -> None:
    src = inspect.getsource(runtime.apply_iris_agent_baseline_overlays)
    assert "apply_iris_agent_cli_shim_overlay" in src
    assert "apply_iris_agent_cli_rename_overlay" in src


def _check_probe_iris_cli_only() -> None:
    names = runtime.AGENT_CLI_PROBE_NAMES
    assert "hermes_cli" not in names
    assert "iris_agent_cli" in names
    assert "iris_cli" in names


def main() -> None:
    _check_overlay_makes_iris_cli_importable()
    _check_skip_without_agent_cli()
    _check_baseline_wires_cli_shim()
    _check_probe_iris_cli_only()
    print("iris_agent_cli_shim ok")


if __name__ == "__main__":
    main()
