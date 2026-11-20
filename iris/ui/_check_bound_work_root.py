"""Bound IDE workspace = sole write/run root. sticky profile.project_root 금지.

BoundRootFail UX: unbound/mismatch/align_failed 가 code·hint·한국어 안내를 담는다.
"""

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
    from iris.ui.control_bindings import (
        BOUND_ROOT_UNBOUND,
        _MSG_BOUND_UNBOUND,
        resolve_bound_work_root,
    )

    window = MagicMock()
    window._conversation_id = 0
    window._bound_slot = None
    window._get_bound_ide_session.return_value = None
    root, err = resolve_bound_work_root(window, {})
    assert root == ""
    assert err == _MSG_BOUND_UNBOUND
    assert "Companion" in err
    assert "ide.open_folder" in err
    assert BOUND_ROOT_UNBOUND == "unbound"


def check_ensure_unbound_has_code_hint() -> None:
    from iris.ui.control_bindings import (
        BOUND_ROOT_UNBOUND,
        ensure_iris_ide_workspace,
    )

    with tempfile.TemporaryDirectory(prefix="iris-bound-ux-") as td:
        want = str(Path(td).resolve())
        window = MagicMock()
        window._control_qt_invoker = None
        window._get_bound_ide_session.return_value = None
        err = ensure_iris_ide_workspace(
            window, want, action="project.write_file", open_folder=lambda _p: ""
        )
        assert err is not None
        assert err.get("ok") is False
        data = err.get("result") or {}
        assert data.get("code") == BOUND_ROOT_UNBOUND, data
        assert data.get("hint") == "ide.open_folder", data
        assert data.get("project_root") == want
        assert data.get("bound_workspace_root") is None
        assert "Companion" in str(err.get("error") or "")
        assert "ide.open_folder" in str(err.get("error") or "")


def check_ensure_align_failed_and_mismatch_codes() -> None:
    from iris.ui.control_bindings import (
        BOUND_ROOT_ALIGN_FAILED,
        BOUND_ROOT_MISMATCH,
        ensure_iris_ide_workspace,
    )

    with tempfile.TemporaryDirectory(prefix="iris-bound-ux-") as td:
        bound = Path(td) / "bound"
        want = Path(td) / "want"
        bound.mkdir()
        want.mkdir()
        bound_s = str(bound.resolve())
        want_s = str(want.resolve())
        session = SimpleNamespace(
            ide_id="iris_ide",
            workspace_root=bound_s,
            mode="workspace",
            hwnd=1,
            pid=1,
        )
        window = MagicMock()
        window._control_qt_invoker = None
        window._get_bound_ide_session.return_value = session

        fail = ensure_iris_ide_workspace(
            window,
            want_s,
            action="project.run",
            open_folder=lambda _p: "companion not entered",
        )
        assert fail is not None
        data = fail.get("result") or {}
        assert data.get("code") == BOUND_ROOT_ALIGN_FAILED, data
        assert data.get("hint") == "ide.open_folder"
        assert data.get("project_root") == want_s
        assert data.get("bound_workspace_root") == bound_s
        assert "ide.open_folder" in str(fail.get("error") or "")

        # open succeeds but root stays on old bound → mismatch
        stuck = ensure_iris_ide_workspace(
            window,
            want_s,
            action="project.write_file",
            open_folder=lambda _p: "",
        )
        assert stuck is not None
        data2 = stuck.get("result") or {}
        assert data2.get("code") == BOUND_ROOT_MISMATCH, data2
        assert data2.get("hint") == "ide.open_folder"
        assert data2.get("project_root") == want_s
        assert data2.get("bound_workspace_root") == bound_s
        assert "project_root=" in str(stuck.get("error") or "")
        assert "bound=" in str(stuck.get("error") or "")


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
    check_ensure_unbound_has_code_hint()
    check_ensure_align_failed_and_mismatch_codes()
    check_no_sticky_save_on_open()
    check_project_actions_use_resolver()
    print("bound_work_root check ok")


if __name__ == "__main__":
    main()
