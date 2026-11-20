"""F3 — rename overlay materializes real iris_agent_cli; hermes_cli becomes reverse shim.

Probe drops hermes_cli. Tempdir only — never force-rename a live locked tree.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_cli_rename
"""

from __future__ import annotations

import importlib
import inspect
import sys
import tempfile
from pathlib import Path

from iris.infrastructure import agent_runtime as runtime
from iris.system.iris_agent_cli_rename_overlay import (
    apply_iris_agent_cli_rename_overlay,
    iris_agent_cli_is_real_package,
    iris_agent_cli_rename_applied,
)
from iris.system.iris_agent_cli_shim_overlay import apply_iris_agent_cli_shim_overlay


def _tiny_agent_tree(root: Path) -> None:
    hermes = root / "hermes_cli"
    hermes.mkdir()
    (hermes / "__init__.py").write_text(
        '"""tiny hermes_cli."""\nMARKER = "upstream"\n',
        encoding="utf-8",
    )
    (hermes / "main.py").write_text(
        "def main():\n    return 0\n",
        encoding="utf-8",
    )
    tools = hermes / "tools"
    tools.mkdir()
    (tools / "__init__.py").write_text(
        '"""hermes_cli.tools stub."""\nX = 1\n',
        encoding="utf-8",
    )


def _check_rename_makes_real_iris_agent_cli() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _tiny_agent_tree(root)
        msgs = apply_iris_agent_cli_rename_overlay(root)
        assert msgs
        assert any("rename" in m.lower() or "f3" in m.lower() for m in msgs)

        iris = root / "iris_agent_cli"
        assert iris.is_dir()
        assert iris_agent_cli_is_real_package(root)
        init_text = (iris / "__init__.py").read_text(encoding="utf-8")
        assert "hermes_cli" not in init_text or "iris_agent_cli" in init_text
        assert "iris_agent_cli" in init_text
        assert "MARKER" in init_text
        tools_init = (iris / "tools" / "__init__.py").read_text(encoding="utf-8")
        assert "iris_agent_cli.tools" in tools_init
        assert "hermes_cli" not in tools_init

        hermes_init = (root / "hermes_cli" / "__init__.py").read_text(encoding="utf-8")
        assert "iris_agent_cli" in hermes_init
        assert "from iris_agent_cli import" in hermes_init

        iris_cli_init = (root / "iris_cli" / "__init__.py").read_text(encoding="utf-8")
        assert "from iris_agent_cli import" in iris_cli_init

        assert iris_agent_cli_rename_applied(root)

        sys.path.insert(0, str(root))
        try:
            for name in ("iris_agent_cli", "hermes_cli", "iris_cli"):
                sys.modules.pop(name, None)
            mod = importlib.import_module("iris_agent_cli")
            assert getattr(mod, "MARKER", None) == "upstream"
            hermes = importlib.import_module("hermes_cli")
            assert getattr(hermes, "MARKER", None) == "upstream"
        finally:
            sys.path.remove(str(root))
            for name in ("iris_agent_cli", "hermes_cli", "iris_cli"):
                sys.modules.pop(name, None)

        again = apply_iris_agent_cli_rename_overlay(root)
        assert any("already" in m.lower() for m in again)


def _check_f2_skips_when_f3_real() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _tiny_agent_tree(root)
        apply_iris_agent_cli_rename_overlay(root)
        msgs = apply_iris_agent_cli_shim_overlay(root)
        assert msgs
        blob = " ".join(msgs).lower()
        assert "superseded" in blob or "skipped" in blob or "real" in blob
        # Must not overwrite real package with forward hermes re-export.
        init = (root / "iris_agent_cli" / "__init__.py").read_text(encoding="utf-8")
        assert "from hermes_cli import" not in init


def _check_probe_drops_agent_cli() -> None:
    if not hasattr(runtime, "AGENT_CLI_PROBE_NAMES"):
        return
    names = runtime.AGENT_CLI_PROBE_NAMES
    assert names == ("iris_agent_cli", "iris_cli")
    assert "hermes_cli" not in names
    if not hasattr(runtime, "agent_cli_probe_code"):
        return
    snippet = runtime.agent_cli_probe_code("aiohttp")
    assert "iris_agent_cli" in snippet
    assert "hermes_cli" not in snippet


def _check_baseline_wires_rename() -> None:
    src = inspect.getsource(runtime.apply_iris_agent_baseline_overlays)
    assert "apply_iris_agent_cli_rename_overlay" in src


def _check_soft_fail_missing_agent() -> None:
    with tempfile.TemporaryDirectory() as td:
        msgs = apply_iris_agent_cli_rename_overlay(Path(td))
        assert msgs
        assert any("missing" in m.lower() or "skipped" in m.lower() for m in msgs)


def _check_reverse_shim_forwards_submodules() -> None:
    """hermes_cli.<sub> must resolve into iris_agent_cli via reverse-shim __path__."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _tiny_agent_tree(root)
        apply_iris_agent_cli_rename_overlay(root)

        hermes_pkg = root / "hermes_cli"
        iris_pkg = root / "iris_agent_cli"
        # Submodule lives only under iris_agent_cli — not as a hermes_cli file.
        probe = iris_pkg / "_early_recovery.py"
        probe.write_text(
            '"""fake iris_agent_cli._early_recovery."""\nPROBE = "via-iris-path"\n',
            encoding="utf-8",
        )
        assert not (hermes_pkg / "_early_recovery.py").exists()
        hermes_names = {p.name for p in hermes_pkg.iterdir()}
        assert hermes_names <= {"__init__.py", "main.py", "__pycache__"}

        sys.path.insert(0, str(root))
        drop = (
            "iris_agent_cli",
            "hermes_cli",
            "iris_cli",
            "iris_agent_cli._early_recovery",
            "hermes_cli._early_recovery",
        )
        try:
            for name in drop:
                sys.modules.pop(name, None)
            hermes = importlib.import_module("hermes_cli")
            iris = importlib.import_module("iris_agent_cli")
            assert list(hermes.__path__) == list(iris.__path__)
            sub = importlib.import_module("hermes_cli._early_recovery")
            assert getattr(sub, "PROBE", None) == "via-iris-path"
            assert sub.__name__ == "hermes_cli._early_recovery"
        finally:
            sys.path.remove(str(root))
            for name in drop:
                sys.modules.pop(name, None)


def main() -> None:
    _check_rename_makes_real_iris_agent_cli()
    _check_f2_skips_when_f3_real()
    _check_probe_drops_agent_cli()
    _check_baseline_wires_rename()
    _check_soft_fail_missing_agent()
    _check_reverse_shim_forwards_submodules()
    print("iris_agent_cli_rename ok")


if __name__ == "__main__":
    main()
