"""project.delete 안전 삭제·OFF_UI 계약.

.venv\\Scripts\\python.exe -m iris.system._check_project_delete
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from iris.system.control_surface import ActionRegistry, runs_off_ui_thread
from iris.system.project_ops import (
    dangerous_delete_reason,
    delete_project_path,
    iris_repo_root,
)
from iris.ui.control_actions.project import project_delete
from iris.ui.control_bindings import _register_actions


def check_ops_delete() -> None:
    with tempfile.TemporaryDirectory() as td:
        parent = Path(td)
        tree = parent / "phase4-doomed"
        (tree / "nested").mkdir(parents=True)
        (tree / "nested" / "a.txt").write_text("x\n", encoding="utf-8")
        out = delete_project_path(tree, parents=[parent])
        assert out["deleted"] is True
        assert out["kind"] == "root"
        assert not tree.exists()
        leaf = parent / "keep"
        leaf.mkdir()
        (leaf / "gone.txt").write_text("y\n", encoding="utf-8")
        assert delete_project_path(leaf, "gone.txt")["kind"] == "file"
        assert not (leaf / "gone.txt").exists()
        assert leaf.exists()
    assert dangerous_delete_reason(Path.home())
    assert dangerous_delete_reason(iris_repo_root())
    try:
        delete_project_path(Path.home(), parents=[Path.home().parent])
        raise AssertionError("home must refuse")
    except ValueError as exc:
        assert "home" in str(exc).lower()
    try:
        delete_project_path(iris_repo_root(), parents=[iris_repo_root().parent])
        raise AssertionError("iris repo must refuse")
    except ValueError as exc:
        assert "Iris repository" in str(exc)


def check_off_ui() -> None:
    assert runs_off_ui_thread("project.delete") is True


def check_control_action() -> None:
    window = MagicMock()
    window._control_qt_invoker = None
    window._get_bound_ide_session.return_value = None
    window._exit_ide_companion = MagicMock()
    window._clear_ide_session = MagicMock()
    window._db = MagicMock()
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    reg = surface.registry
    assert "project.delete" in {a["name"] for a in reg.catalog()}
    with tempfile.TemporaryDirectory() as td:
        parent = Path(td)
        doomed = parent / "ctl-doomed"
        doomed.mkdir()
        (doomed / "f.txt").write_text("z\n", encoding="utf-8")
        # profile parents empty → default_project_parents; inject via monkeypatch on helper
        from iris.ui import control_bindings as cb

        prev = cb._profile_parents
        cb._profile_parents = lambda _w: [parent]  # type: ignore[assignment]
        try:
            out = project_delete(
                window,
                {"project_root": str(doomed)},
            )
        finally:
            cb._profile_parents = prev  # type: ignore[assignment]
        assert out["ok"] is True, out
        assert not doomed.exists()
        refuse = project_delete(window, {"project_root": str(Path.home())})
        assert refuse["ok"] is False
        assert "home" in str(refuse.get("error") or "").lower() or "refusing" in str(
            refuse.get("error") or ""
        ).lower() or "project parent" in str(refuse.get("error") or "")


def main() -> None:
    check_ops_delete()
    check_off_ui()
    check_control_action()
    print("project.delete check ok")


if __name__ == "__main__":
    main()
