"""Phase2: work_root ↔ bound IDE workspace 자동 맞춤 자검.

경로: 일치(open 0회) / 불일치→맞춤성공 / 불일치→맞춤실패.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from iris.ui.control_bindings import ensure_iris_ide_workspace


def _window(session: SimpleNamespace | None) -> MagicMock:
    window = MagicMock()
    window._control_qt_invoker = None
    window._get_bound_ide_session.return_value = session
    window._ui_mode = "ide_companion"
    return window


def check_aligned_skips_open() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-ws-sync-") as td:
        root = str(Path(td).resolve())
        session = SimpleNamespace(
            ide_id="iris_ide",
            workspace_root=root,
            mode="workspace",
            hwnd=1,
            pid=1,
        )
        window = _window(session)
        opened: list[str] = []

        def open_folder(path: str) -> str:
            opened.append(path)
            return ""

        err = ensure_iris_ide_workspace(
            window, root, action="project.write_file", open_folder=open_folder
        )
        assert err is None, err
        assert opened == [], f"expected 0 open_folder calls, got {opened}"


def check_mismatch_opens_then_ok() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-ws-sync-") as td:
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
        window = _window(session)
        opened: list[str] = []

        def open_folder(path: str) -> str:
            opened.append(path)
            session.workspace_root = path
            return ""

        err = ensure_iris_ide_workspace(
            window, want_s, action="project.write_file", open_folder=open_folder
        )
        assert err is None, err
        assert opened == [want_s], opened
        assert str(Path(session.workspace_root).resolve()) == want_s


def check_mismatch_open_fail() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-ws-sync-") as td:
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
        window = _window(session)
        opened: list[str] = []

        def open_folder(path: str) -> str:
            opened.append(path)
            return "companion not entered"

        err = ensure_iris_ide_workspace(
            window, want_s, action="project.run", open_folder=open_folder
        )
        assert err is not None
        assert err.get("ok") is False
        assert err.get("action") == "project.run"
        data = err.get("result") or {}
        assert data.get("project_root") == want_s
        assert data.get("bound_workspace_root") == bound_s
        assert data.get("open_folder_path") == want_s
        assert "companion not entered" in str(data.get("error") or err.get("error") or "")
        assert opened == [want_s]
        assert "call ide.open_folder first" not in str(err.get("error") or "")


def check_silent_reject_gone() -> None:
    src = Path(__file__).resolve().parent / "control_actions" / "project.py"
    text = src.read_text(encoding="utf-8")
    assert "call ide.open_folder first" not in text
    assert "ensure_iris_ide_workspace" in text


def main() -> None:
    check_aligned_skips_open()
    check_mismatch_opens_then_ok()
    check_mismatch_open_fail()
    check_silent_reject_gone()
    print("ok — ide workspace sync (aligned / align-ok / align-fail)")


if __name__ == "__main__":
    main()
