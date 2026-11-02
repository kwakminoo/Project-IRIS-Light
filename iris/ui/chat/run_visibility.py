"""RunVisibility — project.run / write_file → chat ToolShellBlock fields.

No full stdout dump. Turns with zero tools insert nothing (call only after a real action).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MAX_OUTPUT = 400
_MAX_COMMAND = 240


@dataclass(frozen=True)
class VisibilityCard:
    title: str
    command: str
    output: str
    status: str  # ok | error


def _clip(text: str, limit: int = _MAX_OUTPUT) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)] + "…"


def _inner(envelope: dict[str, Any]) -> dict[str, Any]:
    result = envelope.get("result")
    return result if isinstance(result, dict) else {}


def shell_card_from_project_run(envelope: dict[str, Any]) -> VisibilityCard | None:
    """Map control envelope for project.run → shell card. ok and err both card."""
    if not isinstance(envelope, dict):
        return None
    inner = _inner(envelope)
    argv = inner.get("argv")
    if isinstance(argv, (list, tuple)) and argv:
        command = " ".join(str(a) for a in argv)
    else:
        command = str(inner.get("command") or envelope.get("error") or "project.run")
    command = _clip(command, _MAX_COMMAND)
    summary = str(inner.get("summary") or envelope.get("error") or "").strip()
    exit_code = inner.get("exit_code")
    via = str(inner.get("via") or "").strip()
    bits: list[str] = []
    if summary:
        bits.append(summary)
    if exit_code is not None:
        bits.append(f"exit={exit_code}")
    if via:
        bits.append(f"via={via}")
    if not bits:
        bits.append("ok" if envelope.get("ok") else "fail")
    status = "ok" if envelope.get("ok") else "error"
    return VisibilityCard(
        title="Shell",
        command=command,
        output=_clip(" · ".join(bits)),
        status=status,
    )


def write_card_from_project_write(envelope: dict[str, Any]) -> VisibilityCard | None:
    """Short write card when write succeeded on disk (ok or Policy A on_disk)."""
    if not isinstance(envelope, dict):
        return None
    inner = _inner(envelope)
    on_disk = bool(inner.get("on_disk"))
    ok = bool(envelope.get("ok"))
    if not ok and not on_disk:
        return None
    rel = str(inner.get("rel_path") or inner.get("path") or "").strip()
    if not rel:
        return None
    opened = bool(inner.get("opened"))
    bits = [f"opened={str(opened).lower()}"]
    if on_disk and not ok:
        bits.append("on_disk=true")
    via = str(inner.get("via") or "").strip()
    if via:
        bits.append(f"via={via}")
    return VisibilityCard(
        title="Write",
        command=_clip(rel.replace("\\", "/"), _MAX_COMMAND),
        output=_clip(" · ".join(bits)),
        status="ok" if ok else "error",
    )


def card_from_control_result(action: str, envelope: dict[str, Any]) -> VisibilityCard | None:
    name = (action or "").strip()
    if name == "project.run":
        return shell_card_from_project_run(envelope)
    if name == "project.write_file":
        return write_card_from_project_write(envelope)
    return None


def insert_visibility_card(chat: Any, card: VisibilityCard) -> str | None:
    """Reuse ChatPanel.insert_tool_block. Returns block_id or None."""
    insert = getattr(chat, "insert_tool_block", None)
    if not callable(insert) or card is None:
        return None
    return insert(
        title=card.title,
        command=card.command,
        output=card.output,
        status=card.status,
    )


if __name__ == "__main__":
    run_ok = {
        "ok": True,
        "action": "project.run",
        "result": {
            "summary": "exit 0 · ok · 3 lines out",
            "exit_code": 0,
            "via": "theia_terminal",
            "argv": ["python", "print_calendar.py"],
            "stdout": "x" * 5000,
        },
    }
    card = shell_card_from_project_run(run_ok)
    assert card is not None
    assert card.command == "python print_calendar.py"
    assert "exit=0" in card.output
    assert "via=theia_terminal" in card.output
    assert "xxxx" not in card.output
    assert len(card.output) <= _MAX_OUTPUT
    assert card.status == "ok"

    run_err = {
        "ok": False,
        "action": "project.run",
        "error": "exit 1",
        "result": {"summary": "exit 1 · fail", "exit_code": 1, "via": "theia_terminal", "argv": ["pip", "install", "x"]},
    }
    err_card = shell_card_from_project_run(run_err)
    assert err_card is not None and err_card.status == "error"
    assert "pip install x" in err_card.command

    write_ok = {
        "ok": True,
        "action": "project.write_file",
        "result": {"rel_path": "src/a.py", "opened": True, "on_disk": True, "via": "iris_ide_bridge"},
    }
    w = write_card_from_project_write(write_ok)
    assert w is not None and w.title == "Write" and w.command == "src/a.py"
    assert "opened=true" in w.output and w.status == "ok"

    write_disk_only = {
        "ok": False,
        "error": "open timeout",
        "result": {"rel_path": "long.py", "opened": False, "on_disk": True},
    }
    d = write_card_from_project_write(write_disk_only)
    assert d is not None and d.status == "error" and "on_disk=true" in d.output

    assert write_card_from_project_write({"ok": False, "result": {}}) is None
    assert card_from_control_result("wiki.search", run_ok) is None
    assert card_from_control_result("project.run", run_ok) is not None
    print("run_visibility ok")
