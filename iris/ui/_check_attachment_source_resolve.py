"""attachment_id resolve for content.extract / content.dump_lab_scripts.

Observables: prefer attachment_id → absolute Path; absolute path still works for
extract; unknown id fails with attachment.list / get_state guidance.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from iris.knowledge.lab_script_dump import LabDumpResult
from iris.runtime.attachment_store import AttachmentStore
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.wiki import register_wiki_actions


def _window_with_store(store: AttachmentStore) -> MagicMock:
    window = MagicMock()
    window._chat_session = MagicMock()
    window._chat_session.attachments = store
    window._get_bound_ide_session.return_value = None
    window._ui_mode = "assistant"
    window._workspace_mode = "home"
    window._agent_online = False
    window._settings.agent_enabled = True
    window._settings.model_name = "test"
    window._settings.ollama_model = "test"
    window._settings.ollama_base_url = "http://127.0.0.1:11434"
    window._db = MagicMock()
    window._iris_wiki = MagicMock()
    window._chat = MagicMock()
    window._chat.current_model.return_value = "test"
    window._model_switch = MagicMock()
    window._model_switch.history_settings = MagicMock()
    window._current_project_root = MagicMock(return_value="")
    window._saved_model = "test"
    return window


def check_extract_by_attachment_id() -> None:
    store = AttachmentStore()
    with tempfile.TemporaryDirectory(prefix="iris-att-src-") as td:
        root = Path(td)
        f = root / "notes.txt"
        f.write_text("hello attachment extract", encoding="utf-8")
        store.attach([str(f)])
        aid = next(iter(store.roots))
        window = _window_with_store(store)
        reg = ActionRegistry()
        register_wiki_actions(window, reg)

        by_id = reg.invoke("content.extract", {"attachment_id": aid})
        assert by_id["ok"] is True, by_id
        assert "hello attachment extract" in str(by_id["result"]["text"])

        by_name = reg.invoke("content.extract", {"attachment_id": "notes.txt"})
        assert by_name["ok"] is True, by_name

        abs_ok = reg.invoke("content.extract", {"source": str(f)})
        assert abs_ok["ok"] is True, abs_ok
        assert "hello attachment extract" in str(abs_ok["result"]["text"])

        unknown = reg.invoke("content.extract", {"attachment_id": "missing-file.bin"})
        assert unknown["ok"] is False
        err = str(unknown.get("error") or "")
        assert "attachment.list" in err or "get_state" in err, err


def check_dump_by_attachment_id() -> None:
    store = AttachmentStore()
    with tempfile.TemporaryDirectory(prefix="iris-att-dump-") as td:
        root = Path(td)
        pdf = root / "lecture.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        store.attach([str(pdf)])
        aid = next(iter(store.roots))
        project = root / "proj"
        project.mkdir()

        window = _window_with_store(store)
        window._current_project_root = MagicMock(return_value=str(project))
        captured: dict[str, object] = {}

        def _fake_dump(source, proj_root, out_subdir="labs", vision_reader=None, **_kw):
            captured["source"] = str(source)
            captured["root"] = str(proj_root)
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
                {"attachment_id": aid, "out_dir": "labs"},
            )
            assert out["ok"] is True, out
            assert Path(str(captured["source"])).resolve() == pdf.resolve(), captured
            assert Path(str(captured["root"])).resolve() == project.resolve(), captured
        finally:
            dump_mod.dump_lab_scripts = real  # type: ignore[assignment]


def check_absolute_file_path_refuses_folder() -> None:
    store = AttachmentStore()
    with tempfile.TemporaryDirectory(prefix="iris-att-folder-") as td:
        folder = Path(td) / "bundle"
        folder.mkdir()
        (folder / "a.txt").write_text("x", encoding="utf-8")
        store.attach([str(folder)])
        aid = next(iter(store.roots))
        try:
            store.absolute_file_path(aid)
            raise AssertionError("folder attachment must raise")
        except ValueError as exc:
            assert "폴더" in str(exc) or "folder" in str(exc).casefold()


def main() -> None:
    check_extract_by_attachment_id()
    check_dump_by_attachment_id()
    check_absolute_file_path_refuses_folder()
    print("attachment source resolve ok")


if __name__ == "__main__":
    main()
