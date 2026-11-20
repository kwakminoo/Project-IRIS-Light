"""Agent must not switch IDE workspace when Companion is bound; PDF via dump/extract only."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import (
    peek_bound_root,
    refuse_agent_workspace_switch,
    _register_actions,
)


def _bound_window(root: Path) -> MagicMock:
    window = MagicMock()
    window._control_qt_invoker = None
    window._db = object()
    window._conversation_id = 0
    window._bound_slot = None
    window._ui_mode = "ide_companion"
    window._get_bound_ide_session.return_value = SimpleNamespace(
        workspace_root=str(root.resolve()),
        mode="workspace",
        ide_id="iris_ide",
        active=True,
        hwnd=1,
        pid=1,
        source="test",
        last_seen_at=0.0,
    )
    return window


def _unbound_window() -> MagicMock:
    window = MagicMock()
    window._control_qt_invoker = None
    window._db = object()
    window._conversation_id = 0
    window._bound_slot = None
    window._ui_mode = "chat"
    window._get_bound_ide_session.return_value = None
    return window


def _registry(window: MagicMock) -> ActionRegistry:
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return surface.registry


def check_peek_and_refuse_shape() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-lock-") as td:
        bound = Path(td) / "ws"
        bound.mkdir()
        window = _bound_window(bound)
        root = peek_bound_root(window)
        assert root is not None
        assert Path(root) == bound.resolve()

        refused = refuse_agent_workspace_switch("project.open_similar", root)
        assert refused is not None
        assert refused["ok"] is False
        assert refused["action"] == "project.open_similar"
        payload = refused.get("result") or {}
        assert payload.get("reason") == "agent_workspace_locked"
        assert Path(str(payload.get("bound_root"))) == bound.resolve()

    assert peek_bound_root(_unbound_window()) is None
    assert refuse_agent_workspace_switch("ide.open_folder", None) is None


def check_open_similar_and_open_folder_refuse_when_bound() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-lock-open-") as td:
        bound = Path(td) / "on_screen"
        bound.mkdir()
        window = _bound_window(bound)
        window._open_ide_folder = MagicMock(return_value="")
        reg = _registry(window)

        similar = reg.invoke("project.open_similar", {"query": "AI guitar tab"})
        assert similar["ok"] is False
        assert (similar.get("result") or {}).get("reason") == "agent_workspace_locked"
        window._open_ide_folder.assert_not_called()

        opened = reg.invoke("ide.open_folder", {"path": str(bound)})
        assert opened["ok"] is False
        assert (opened.get("result") or {}).get("reason") == "agent_workspace_locked"
        window._open_ide_folder.assert_not_called()


def check_unbound_open_folder_still_invokes() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-lock-free-") as td:
        folder = Path(td) / "proj"
        folder.mkdir()
        window = _unbound_window()
        window._open_ide_folder = MagicMock(return_value="")
        window._ui_mode = "ide_companion"
        reg = _registry(window)
        opened = reg.invoke("ide.open_folder", {"path": str(folder), "new_window": True})
        assert opened["ok"] is True
        window._open_ide_folder.assert_called_once()


def check_dump_lab_scripts_uses_bound_ignores_mismatch() -> None:
    from iris.knowledge.lab_script_dump import LabDumpResult
    from iris.runtime.chat_worktree import reset_worktrees
    from iris.ui.control_actions.wiki import register_wiki_actions

    reset_worktrees()
    with tempfile.TemporaryDirectory(prefix="iris-lock-dump-") as td:
        bound = Path(td) / "bound"
        other = Path(td) / "other"
        bound.mkdir()
        other.mkdir()
        pdf = Path(td) / "lecture.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")

        window = _bound_window(bound)
        captured: dict[str, object] = {}

        def _fake_dump(source, root, out_subdir="labs", vision_reader=None):
            captured["root"] = str(root)
            captured["source"] = str(source)
            captured["out_subdir"] = out_subdir
            return LabDumpResult(
                programs=(),
                written=(),
                errors=("no labels",),
                truncated_pages=False,
                source_pdf=str(source),
            )

        import iris.knowledge.lab_script_dump as dump_mod

        real = dump_mod.dump_lab_scripts
        dump_mod.dump_lab_scripts = _fake_dump  # type: ignore[assignment]
        try:
            reg = ActionRegistry()
            register_wiki_actions(window, reg)
            out = reg.invoke(
                "content.dump_lab_scripts",
                {
                    "source": str(pdf),
                    "project_root": str(other),
                    "out_dir": "labs",
                },
            )
            assert out["ok"] is True, out
            assert Path(str(captured["root"])).resolve() == bound.resolve(), captured
        finally:
            dump_mod.dump_lab_scripts = real  # type: ignore[assignment]


def check_local_read_file_rejects_pdf() -> None:
    from iris.ui.control_actions.local_files import register_local_file_actions

    with tempfile.TemporaryDirectory(prefix="iris-lock-pdf-") as td:
        pdf = Path(td) / "notes.PDF"
        pdf.write_bytes(b"%PDF-1.4\nfake")
        window = _unbound_window()
        reg = ActionRegistry()
        register_local_file_actions(window, reg)
        # Scope SYSTEM so path would otherwise be readable — PDF must still refuse.
        from iris.storage import local_access_prefs as prefs

        real_scope = prefs.load_local_read_scope
        prefs.load_local_read_scope = lambda _db=None: prefs.SYSTEM  # type: ignore[assignment]
        try:
            out = reg.invoke("local.read_file", {"path": str(pdf)})
        finally:
            prefs.load_local_read_scope = real_scope  # type: ignore[assignment]
        assert out["ok"] is False
        err = str(out.get("error") or "")
        assert "dump_lab_scripts" in err or "content.extract" in err
        assert "content.extract" in err or "extract" in err.casefold()


def check_agent_registry_handlers_name_lock() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "infrastructure"
        / "agent_tool_registry.py"
    ).read_text(encoding="utf-8")
    assert "agent_workspace_locked" in src
    assert "_live_bound_root" in src or "peek_bound_root" in src or "bound_root" in src


def main() -> None:
    check_peek_and_refuse_shape()
    check_open_similar_and_open_folder_refuse_when_bound()
    check_unbound_open_folder_still_invokes()
    check_dump_lab_scripts_uses_bound_ignores_mismatch()
    check_local_read_file_rejects_pdf()
    check_agent_registry_handlers_name_lock()
    print("agent_workspace_lock check ok")


if __name__ == "__main__":
    main()
