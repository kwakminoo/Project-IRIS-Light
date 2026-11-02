"""Bound IDE workspace = sole write/run root. sticky profile.project_root 금지."""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def check_resolve_prefers_bound_not_profile() -> None:
    from iris.runtime.chat_worktree import reset_worktrees
    from iris.ui.control_bindings import resolve_bound_work_root

    reset_worktrees()
    with tempfile.TemporaryDirectory(prefix="iris-bound-") as td:
        bound = Path(td) / "on_screen"
        bound.mkdir()
        bound_s = str(bound.resolve())

        window = MagicMock()
        window._db = object()
        window._conversation_id = 0
        window._bound_slot = None
        window._get_bound_ide_session.return_value = SimpleNamespace(
            workspace_root=bound_s,
            mode="workspace",
            ide_id="iris_ide",
        )

        root, err = resolve_bound_work_root(window, {})
        assert err == "", err
        assert Path(root) == Path(bound_s), (root, bound_s)

        # sticky profile must not be consulted (no profile mock needed)
        assert "load_user_profile" not in inspect.getsource(resolve_bound_work_root)


def check_resolve_requires_bound_when_empty() -> None:
    from iris.ui.control_bindings import resolve_bound_work_root

    window = MagicMock()
    window._conversation_id = 0
    window._bound_slot = None
    window._get_bound_ide_session.return_value = None
    root, err = resolve_bound_work_root(window, {})
    assert root == ""
    assert "bound IDE workspace" in err


def check_no_sticky_save_on_open() -> None:
    main = Path(__file__).resolve().parent / "window" / "main_window.py"
    text = main.read_text(encoding="utf-8")
    # _open_iris_ide_folder must not assign profile.project_root
    assert "def _open_iris_ide_folder" in text
    start = text.index("def _open_iris_ide_folder")
    end = text.index("\n    def ", start + 1)
    body = text[start:end]
    assert "profile.project_root =" not in body, "sticky save returned in _open_iris_ide_folder"


def check_project_actions_use_resolver() -> None:
    src = Path(__file__).resolve().parent / "control_actions" / "project.py"
    text = src.read_text(encoding="utf-8")
    assert text.count("resolve_bound_work_root") >= 4
    assert "profile.project_root or \"\"" not in text.replace(" ", "")


def main() -> None:
    check_resolve_prefers_bound_not_profile()
    check_resolve_requires_bound_when_empty()
    check_no_sticky_save_on_open()
    check_project_actions_use_resolver()
    print("bound_work_root check ok")


if __name__ == "__main__":
    main()
