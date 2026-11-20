"""IRIS IDE child env must not inherit Iris .venv (integrated-terminal python)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from iris.system.iris_ide_runtime import sanitize_ide_child_env


def _fake_polluted_env(venv: Path, system_bin: Path) -> dict[str, str]:
    scripts = venv / "Scripts"
    qt_bin = venv / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin"
    scripts.mkdir(parents=True, exist_ok=True)
    qt_bin.mkdir(parents=True, exist_ok=True)
    system_bin.mkdir(parents=True, exist_ok=True)
    path = os.pathsep.join(
        [
            str(scripts),
            str(qt_bin),
            str(system_bin),
        ]
    )
    return {
        "VIRTUAL_ENV": str(venv),
        "PYTHONPATH": str(venv / "Lib" / "site-packages"),
        "PYTHONHOME": str(venv),
        "UV_PROJECT": "polluted",
        "CONDA_PREFIX": "polluted",
        "PIP_PYTHON": str(venv / "Scripts" / "python.exe"),
        "PATH": path,
        "IRIS_IDE_KEEP_ME": "before-sanitize",
    }


def _assert_sanitized(cleaned: dict[str, str], *, venv: Path, system_bin: Path) -> None:
    assert "VIRTUAL_ENV" not in cleaned
    assert "PYTHONPATH" not in cleaned
    assert "PYTHONHOME" not in cleaned
    assert "UV_PROJECT" not in cleaned
    assert "CONDA_PREFIX" not in cleaned
    assert "PIP_PYTHON" not in cleaned
    path = cleaned.get("PATH", "")
    parts = [p for p in path.split(os.pathsep) if p]
    venv_norm = str(venv.resolve()).casefold()
    for part in parts:
        part_norm = str(Path(part).resolve()).casefold()
        assert not (
            part_norm == venv_norm or part_norm.startswith(venv_norm + os.sep)
        ), f"PATH still under iris venv: {part!r}"
    system_norm = str(system_bin.resolve()).casefold()
    assert any(
        str(Path(p).resolve()).casefold() == system_norm for p in parts
    ), f"system PATH entry missing: {path!r}"


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        venv = root / ".venv"
        system_bin = root / "System32"
        dirty = _fake_polluted_env(venv, system_bin)

        cleaned = sanitize_ide_child_env(dirty, iris_venv=venv)
        _assert_sanitized(cleaned, venv=venv, system_bin=system_bin)

        again = sanitize_ide_child_env(cleaned, iris_venv=venv)
        assert again == cleaned

        # wire order: sanitize first, then IDE keys must remain
        wired = dict(cleaned)
        wired["PORT"] = "39111"
        wired["THEIA_CONFIG_DIR"] = str(root / "theia-cfg")
        wired["IRIS_IDE_WORKSPACE"] = str(root / "ws")
        wired["IRIS_IDE_BRIDGE_PORT"] = "39112"
        wired["IRIS_IDE_BRIDGE_TOKEN"] = "tok"
        wired["IRIS_IDE_STATE_FILE"] = str(root / "state.json")
        wired["IRIS_IDE_STANDALONE_BRIDGE"] = "1"
        assert wired["PORT"] == "39111"
        assert wired["IRIS_IDE_WORKSPACE"] == str(root / "ws")
        assert "VIRTUAL_ENV" not in wired

    print("iris_ide_child_env check ok")


if __name__ == "__main__":
    main()
