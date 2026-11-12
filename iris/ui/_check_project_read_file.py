"""project.read_file — disk UTF-8 dual of write_project_file."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from iris.system.project_ops import read_project_file, write_project_file

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = Path(__file__).resolve().parent / "control_actions" / "action_catalog.json"
_VIBE_SKILL = (
    _ROOT
    / "integrations"
    / "hermes-skills"
    / "iris-control"
    / "iris-vibe-code"
    / "SKILL.md"
)


def main() -> None:
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    entry = next((a for a in catalog if a["name"] == "project.read_file"), None)
    assert entry is not None, "project.read_file missing from action_catalog"
    assert entry.get("risk") == "low"
    assert entry.get("confirm_required") is False
    summary = str(entry.get("summary") or "").lower()
    assert "bound" in summary or "workspace" in summary

    vibe = _VIBE_SKILL.read_text(encoding="utf-8")
    assert "project.read_file" in vibe, "iris-vibe-code SKILL must name project.read_file"
    assert "Disk UTF-8" in vibe or "disk UTF-8" in vibe
    assert "ide.save" in vibe or "ide.edit" in vibe

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        try:
            read_project_file(root, "../x")
            raise AssertionError("escape should fail")
        except ValueError as exc:
            msg = str(exc).lower()
            assert "invalid rel_path" in msg or "escape" in msg

        try:
            read_project_file(root, "missing.txt")
            raise AssertionError("missing should fail")
        except FileNotFoundError:
            pass

        (root / "nul.bin").write_bytes(b"hello\x00world")
        try:
            read_project_file(root, "nul.bin")
            raise AssertionError("NUL binary should fail")
        except ValueError as exc:
            assert "utf-8" in str(exc).lower()

        (root / "big.txt").write_text("x" * 100, encoding="utf-8")
        try:
            read_project_file(root, "big.txt", max_bytes=50)
            raise AssertionError("too-large should fail")
        except ValueError as exc:
            assert "too large" in str(exc).lower()

        (root / "adir").mkdir()
        try:
            read_project_file(root, "adir")
            raise AssertionError("directory should fail")
        except IsADirectoryError:
            pass

        body = "print(1)\n한글\n"
        write_project_file(root, "src/main.py", body)
        raw = (root / "src" / "main.py").read_bytes()
        got = read_project_file(root, "src/main.py")
        assert got["content"] == raw.decode("utf-8")
        assert got["encoding"] == "utf-8"
        assert got["rel_path"] == "src/main.py"
        assert got["bytes"] == len(raw)
        assert got["path"]
        assert "ok" not in got
        assert "print(1)" in got["content"] and "한글" in got["content"]

        from unittest.mock import MagicMock

        from iris.system.control_surface import ActionRegistry
        from iris.ui.control_bindings import _register_actions

        window = MagicMock()
        window._control_qt_invoker = None
        window._get_bound_ide_session.return_value = None
        surface = MagicMock()
        surface.registry = ActionRegistry()
        surface.booting = False
        _register_actions(window, surface)
        surface.registry.set_human_confirm(lambda spec, args: True)
        inv = surface.registry.invoke(
            "project.read_file",
            {"project_root": str(root), "rel_path": "src/main.py"},
        )
        assert inv["ok"] is True
        assert inv["result"]["content"] == got["content"]
        miss = surface.registry.invoke(
            "project.read_file",
            {"project_root": str(root), "rel_path": "nope.py"},
        )
        assert miss["ok"] is False
    print("project.read_file self-check ok")


if __name__ == "__main__":
    main()
