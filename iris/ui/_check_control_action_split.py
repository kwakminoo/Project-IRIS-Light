"""연번 12 — 액션 이름·계약은 같고 등록만 기능별로 나뉘었는지.

카탈로그 스냅샷은 분리 직전 104건이다. 사용자 확인 전 완료 판정은 하지 않는다.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from iris.system.control_surface import ActionRegistry, runs_off_ui_thread
from iris.ui.chat.chat_display import assistant_visible_text
from iris.ui.control_bindings import _register_actions
from iris.ui.window._check_file_drop import check_chat_drag_actions

_CATALOG = Path(__file__).resolve().parent / "control_actions" / "action_catalog.json"


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._get_bound_ide_session.return_value = None
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    return window, surface.registry


def check_invalid_and_write(reg: ActionRegistry, window: MagicMock) -> None:
    missing_content = reg.invoke(
        "project.write_file",
        {"project_root": "C:/tmp", "rel_path": "a.py"},
    )
    assert missing_content["ok"] is False
    assert missing_content["error"] == "content required"

    missing_rel = reg.invoke(
        "project.write_file",
        {"project_root": "C:/tmp", "content": "x"},
    )
    assert missing_rel["ok"] is False
    assert "rel_path" in missing_rel["error"]

    run_missing = reg.invoke("project.run", {"project_root": "C:/no/such/iris-split"})
    assert run_missing["ok"] is False
    assert run_missing["error"].startswith("not a directory:")

    opened = reg.invoke(
        "ide.open_file",
        {"project_root": "C:/tmp"},
    )
    assert opened["ok"] is False
    assert opened["error"] == "path or project_root+rel_path required"

    attached = reg.invoke("chat.attach", {})
    assert attached["ok"] is False
    assert attached["error"] == "path required"

    hermes = reg.invoke("settings.set", {"hermes_enabled": False})
    assert hermes["ok"] is False
    assert "cannot be disabled" in hermes["error"]

    window._settings.ollama_base_url = "http://old"
    applied = reg.invoke("settings.set", {"ollama_base_url": "http://127.0.0.1:11434"})
    assert applied["ok"] is True
    assert window._settings.ollama_base_url == "http://127.0.0.1:11434"
    window._refresh_hermes_health.assert_called()

    with tempfile.TemporaryDirectory() as tmp:
        out = reg.invoke(
            "project.write_file",
            {
                "project_root": tmp,
                "rel_path": "hello.txt",
                "content": "hi\n",
                "open": False,
            },
        )
        assert out["ok"] is True, out.get("error")
        assert (Path(tmp) / "hello.txt").read_text(encoding="utf-8") == "hi\n"
        assert out["result"]["opened"] is False
    window._note_tool_file_write.assert_called_once()


def check_threads() -> None:
    assert runs_off_ui_thread("project.run") is True
    assert runs_off_ui_thread("project.write_file") is False
    assert runs_off_ui_thread("emulator.tap") is True
    assert runs_off_ui_thread("email.list_messages") is True
    assert runs_off_ui_thread("ide.open_file") is False
    assert runs_off_ui_thread("settings.set") is False


def check_summary_and_modules() -> None:
    raw = "요약을 남긴다.\n```python\nprint(1)\n```\nC:\\Users\\secret\\proj\\main.py"
    visible = assistant_visible_text(raw, streaming=False)
    assert "print" not in visible
    assert "secret" not in visible
    assert "요약을 남긴다." in visible
    assert "main.py" in visible
    root = Path(__file__).resolve().parent / "control_actions"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import MainWindow" not in text


def main() -> None:
    window, reg = _surface()
    got = reg.catalog()
    before = json.loads(_CATALOG.read_text(encoding="utf-8"))
    assert got == before, "action catalog drifted"
    names = [a["name"] for a in got]
    assert len(names) == len(set(names)) == 104
    check_invalid_and_write(reg, window)
    check_threads()
    check_summary_and_modules()
    check_chat_drag_actions()
    print("control action split ok")


if __name__ == "__main__":
    main()
