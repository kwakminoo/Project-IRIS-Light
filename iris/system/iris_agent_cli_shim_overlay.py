"""Install-time CLI import shim: iris_agent_cli / iris_cli re-export hermes_cli.

F2 fallback when F3 rename did not materialize a real iris_agent_cli.
When F3 already applied (real package), this overlay is a no-op.
"""

from __future__ import annotations

from pathlib import Path

_SHIM_PACKAGES = ("iris_agent_cli", "iris_cli")
_MARKER = "Iris CLI shim — re-exports hermes_cli"

_INIT_PY = f'''\
"""{_MARKER} (install overlay)."""
from hermes_cli import *  # noqa: F401, F403
'''

_MAIN_PY = '''\
"""Forward ``-m {pkg}.main`` to hermes_cli.main."""
from hermes_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
'''


def apply_iris_agent_cli_shim_overlay(agent_root: Path) -> list[str]:
    """Write thin iris_agent_cli / iris_cli packages. Soft-fail; never raise."""
    root = Path(agent_root)
    # F3 supersedes: real iris_agent_cli already owns the CLI surface.
    try:
        from iris.system.iris_agent_cli_rename_overlay import (
            iris_agent_cli_is_real_package,
            iris_agent_cli_rename_applied,
        )
    except ImportError:
        iris_agent_cli_is_real_package = None  # type: ignore[assignment]
        iris_agent_cli_rename_applied = None  # type: ignore[assignment]

    if iris_agent_cli_rename_applied is not None and iris_agent_cli_rename_applied(root):
        return ["cli shim: superseded by F3 rename"]
    if iris_agent_cli_is_real_package is not None and iris_agent_cli_is_real_package(root):
        return ["cli shim: iris_agent_cli real package — skipped"]

    hermes = root / "hermes_cli"
    if not hermes.is_dir() and not (hermes.with_suffix(".py")).is_file():
        return ["cli shim: hermes_cli missing — skipped"]

    if _shims_already_present(root):
        return ["cli shim: already present"]

    written: list[str] = []
    for pkg in _SHIM_PACKAGES:
        pkg_dir = root / pkg
        try:
            pkg_dir.mkdir(parents=True, exist_ok=True)
            init_path = pkg_dir / "__init__.py"
            if not _file_has_marker(init_path):
                init_path.write_text(_INIT_PY, encoding="utf-8", newline="\n")
                written.append(f"{pkg}/__init__.py")
            main_path = pkg_dir / "main.py"
            if not _file_has_main_forward(main_path):
                main_path.write_text(
                    _MAIN_PY.format(pkg=pkg), encoding="utf-8", newline="\n"
                )
                written.append(f"{pkg}/main.py")
        except OSError as exc:
            return [f"cli shim: write fail ({pkg}): {exc}"]

    if not written and _shims_already_present(root):
        return ["cli shim: already present"]
    if not written:
        return ["cli shim: already present"]
    return [f"cli shim: wrote {', '.join(written)}"]


def _file_has_marker(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _MARKER in text or "from hermes_cli import" in text


def _file_has_main_forward(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "hermes_cli.main" in text


def _shims_already_present(root: Path) -> bool:
    for pkg in _SHIM_PACKAGES:
        pkg_dir = root / pkg
        if not _file_has_marker(pkg_dir / "__init__.py"):
            return False
        if not _file_has_main_forward(pkg_dir / "main.py"):
            return False
    return True
