"""One wait per shell card. The worker blocks until that card's click decides."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from iris.ui.chat.run_visibility import card_from_control_result, insert_visibility_card
from iris.ui.chat.shell_approval import ApprovalState, preview_command, should_auto_run


@dataclass
class _Wait:
    event: threading.Event
    decision: str = ""


_lock = threading.Lock()
_waits: dict[str, _Wait] = {}


def arm(block_id: str) -> None:
    with _lock:
        _waits[block_id] = _Wait(event=threading.Event())


def decide(block_id: str, decision: str) -> None:
    with _lock:
        slot = _waits.get(block_id)
        if slot is None:
            return
        slot.decision = decision
        slot.event.set()


def take(block_id: str) -> str:
    with _lock:
        slot = _waits.get(block_id)
    if slot is None:
        # Nothing was armed. Waiting here would leave the worker blocked.
        return ""
    slot.event.wait()
    with _lock:
        if _waits.get(block_id) is slot:
            _waits.pop(block_id, None)
    return slot.decision


def _skipped() -> dict[str, Any]:
    return {
        "ok": False,
        "action": "project.run",
        "error": "skipped",
        "result": {"summary": "Skipped"},
    }


def _paint_result(chat: Any, card: Any, block_id: str) -> None:
    if block_id:
        replace = getattr(chat, "replace_tool_block", None)
        if callable(replace):
            try:
                if replace(
                    block_id,
                    title=card.title,
                    command=card.command,
                    output=card.output,
                    status=card.status,
                    phase="done",
                ):
                    return
            except Exception:
                pass
    insert_visibility_card(chat, card)


def gate_project_run(
    args: dict,
    action: Callable[[dict], dict],
    *,
    chat: Any | None,
    on_ui_thread: bool,
    approval: ApprovalState,
    wait: Callable[[str], str],
    on_ui: Callable[[Callable[[], Any]], Any] | None = None,
) -> dict:
    payload = args if isinstance(args, dict) else {}
    command = preview_command(payload)

    def _ui(fn: Callable[[], Any]) -> Any:
        if on_ui is None:
            return fn()
        return on_ui(fn)

    def _finish(result: Any, block_id: str = "") -> dict:
        envelope = result if isinstance(result, dict) else {}
        try:
            card = card_from_control_result("project.run", envelope)
        except Exception:
            card = None
        if card is not None and chat is not None:
            try:
                _ui(lambda: _paint_result(chat, card, block_id))
            except Exception:
                pass
        return result if isinstance(result, dict) else envelope

    def _run(block_id: str = "") -> dict:
        return _finish(action(payload), block_id)

    can_insert = chat is not None and callable(getattr(chat, "insert_tool_block", None))
    if on_ui_thread or not can_insert or should_auto_run(approval, command):
        return _run()

    def _post() -> str:
        block_id = str(
            chat.insert_tool_block(
                title="Shell",
                command=command,
                output="",
                status="ok",
                phase="pending",
            )
            or ""
        ).strip()
        if block_id:
            arm(block_id)
        return block_id

    try:
        block_id = str(_ui(_post) or "").strip()
    except Exception:
        block_id = ""
    if not block_id:
        return _run()
    if wait(block_id) not in ("run", "always"):
        return _skipped()
    return _run(block_id)
