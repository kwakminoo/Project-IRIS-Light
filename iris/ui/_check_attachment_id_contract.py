"""AttachmentRef id contract — Hermes must copy/import by id, not host paths.

Observables: get_state.attachments, attachment.list, resolve-by-unique-filename,
refuse path/unknown, confirm_required on copy_to/move_to.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from iris.infrastructure.tool_capability import PHASE4_ALLOWLIST
from iris.runtime.attachment_store import AttachmentRef, AttachmentStore
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._get_bound_ide_session.return_value = None
    window._ui_mode = "assistant"
    window._workspace_mode = "home"
    window._agent_online = False
    window._settings.agent_enabled = True
    window._settings.model_name = "test"
    window._settings.ollama_model = "test"
    window._selected_email_account_id = ""
    window._calendar_page = None
    window._db = MagicMock()
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return window, surface.registry


def _attach_two_named(store: AttachmentStore, tmp: Path, name: str) -> list[str]:
    a = tmp / "a"
    b = tmp / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    fa = a / name
    fb = b / name
    fa.write_text("one", encoding="utf-8")
    fb.write_text("two", encoding="utf-8")
    store.attach([str(fa), str(fb)])
    return [fa.name, fb.name]


def check_ref_shape_and_list() -> None:
    store = AttachmentStore()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "notes.txt"
        f.write_text("hello", encoding="utf-8")
        store.attach([str(f)])
        refs = store.list_refs()
        assert len(refs) == 1
        ref = refs[0]
        assert isinstance(ref, AttachmentRef)
        assert set(ref.as_dict()) == {"id", "filename", "size", "mime"}
        assert len(ref.id) == 32 and all(c in "0123456789abcdef" for c in ref.id)
        assert ref.filename == "notes.txt"
        assert ref.size == 5
        assert "path" not in ref.as_dict()
        assert "\\" not in ref.filename
        assert "/" not in ref.filename or ref.filename.count("/") == 0


def check_resolve_rules() -> None:
    store = AttachmentStore()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "report.pdf"
        f.write_bytes(b"%PDF")
        store.attach([str(f)])
        aid = next(iter(store.roots))

        ok = store.resolve_id(aid)
        assert ok.id == aid and ok.error is None

        by_name = store.resolve_id("report.pdf")
        assert by_name.id == aid and by_name.error is None

        pathish = store.resolve_id(str(f))
        assert pathish.id is None and pathish.error
        assert "attachment.list" in pathish.error or "get_state" in pathish.error

        unknown = store.resolve_id("no-such-file.bin")
        assert unknown.id is None and unknown.error
        assert "attachment.list" in unknown.error or "get_state" in unknown.error

        _attach_two_named(store, root / "dup", "same.txt")
        amb = store.resolve_id("same.txt")
        assert amb.id is None
        assert amb.candidates and len(amb.candidates) >= 2
        assert all(set(c) == {"id", "filename", "size", "mime"} for c in amb.candidates)


def check_control_surface() -> None:
    window, reg = _surface()
    store = AttachmentStore()
    window._chat_session = MagicMock()
    window._chat_session.attachments = store

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "slide.pptx"
        f.write_bytes(b"PK")
        store.attach([str(f)])
        aid = next(iter(store.roots))

        listed = reg.invoke("attachment.list", {})
        assert listed["ok"] is True, listed.get("error")
        items = listed["result"]["attachments"]
        assert items == [{"id": aid, "filename": "slide.pptx", "size": 2, "mime": items[0]["mime"]}]
        assert all("path" not in row and "full_path" not in row for row in items)

        state = reg.invoke("get_state", {})
        assert state["ok"] is True, state.get("error")
        attachments = state["result"]["attachments"]
        assert attachments == items

        dest = root / "out" / "slide.pptx"
        dest.parent.mkdir()
        copied = reg.invoke(
            "attachment.copy_to",
            {"attachment_id": "slide.pptx", "destination": str(dest.parent)},
        )
        assert copied["ok"] is True, copied.get("error")
        assert dest.is_file()

        bad = reg.invoke(
            "attachment.copy_to",
            {"attachment_id": str(f), "destination": str(dest.parent)},
        )
        assert bad["ok"] is False
        assert "attachment.list" in bad["error"] or "get_state" in bad["error"]
        assert bad.get("result", {}).get("candidates") in (None, [], ()) or "candidates" in (
            bad.get("result") or {}
        )

        _attach_two_named(store, root / "dup", "same.txt")
        amb = reg.invoke(
            "attachment.move_to",
            {"attachment_id": "same.txt", "destination": str(dest.parent)},
        )
        assert amb["ok"] is False
        cands = (amb.get("result") or {}).get("candidates") or []
        assert len(cands) >= 2

    assert reg.spec("attachment.copy_to").confirm_required is True
    assert reg.spec("attachment.move_to").confirm_required is True
    assert reg.spec("attachment.list").confirm_required is False
    assert "attachment.list" in PHASE4_ALLOWLIST.names()


def main() -> None:
    check_ref_shape_and_list()
    check_resolve_rules()
    check_control_surface()
    print("attachment id contract ok")


if __name__ == "__main__":
    main()
