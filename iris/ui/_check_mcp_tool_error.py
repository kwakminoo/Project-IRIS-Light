"""도구 실행 오류는 Hermes 연결 실패 횟수에 들어가지 않는다.

Hermes mcp_tool.py는 isError 결과를 tool_error(JSON에 error 키)로 바꾸고
그 키를 연속 실패로 센다. 실행 오류는 isError를 켜지 않고 ok=false만 남긴다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from iris.mcp.iris_control_stdio import _tool_result
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions

_THRESHOLD = 3


def _hermes_count(previous: int, mcp_result: dict) -> int:
    """isError면 연결 실패로 센다. 아니면 전송은 된 것이므로 0으로 되돌린다."""
    if mcp_result["isError"]:
        return previous + 1
    return 0


def _locked(count: int) -> bool:
    return count >= _THRESHOLD


def check_business_errors_do_not_lock() -> None:
    cases = [
        {"ok": False, "action": "ide.open_file", "error": "file not found: apple.txt"},
        {"ok": False, "action": "ide.open_file", "error": "path or project_root+rel_path required"},
        {"ok": False, "action": "project.open_folder", "error": "unknown action: project.open_folder"},
        {"ok": False, "action": "ide.open_file", "error": "path escapes workspace"},
    ]
    count = 0
    for payload in cases:
        result = _tool_result(payload)
        assert result["isError"] is False, payload
        assert '"ok": false' in result["content"][0]["text"]
        count = _hermes_count(count, result)
        assert not _locked(count), payload
    ok = _tool_result({"ok": True, "action": "ping", "error": None})
    assert ok["isError"] is False
    count = _hermes_count(count, ok)
    assert count == 0


def check_transport_still_locks() -> None:
    down = {
        "ok": False,
        "error": "Iris control unreachable at http://127.0.0.1:8765. Start Iris Light first.",
        "transport": True,
    }
    count = 0
    for _ in range(_THRESHOLD):
        result = _tool_result(down)
        assert result["isError"] is True
        count = _hermes_count(count, result)
    assert _locked(count)


def check_missing_file_is_not_created() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        window = MagicMock()
        window._control_qt_invoker = None
        window._get_bound_ide_session.return_value = SimpleNamespace(
            ide_id="iris_ide",
            workspace_root=str(root),
            mode="workspace",
            hwnd=1,
            active=True,
        )
        surface = MagicMock()
        surface.registry = reg = ActionRegistry()
        surface.booting = False
        _register_actions(window, surface)
        missing = reg.invoke("ide.open_file", {"path": "apple.txt"})
        assert missing["ok"] is False
        assert "file not found" in missing["error"]
        assert not (root / "apple.txt").exists()
        assert not (root / "iris_generated.py").exists()
        dotted = reg.invoke("ide.open_file", {"path": "apple.txt.txt"})
        assert dotted["ok"] is False
        assert not (root / "apple.txt").exists()
        (root / "apple.txt.txt").write_text("keep", encoding="utf-8")
        assert (root / "apple.txt.txt").read_text(encoding="utf-8") == "keep"


def main() -> None:
    check_business_errors_do_not_lock()
    check_transport_still_locks()
    check_missing_file_is_not_created()
    print("mcp tool error vs transport ok")


if __name__ == "__main__":
    main()
