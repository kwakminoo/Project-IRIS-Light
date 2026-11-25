"""One wait per shell card. The worker blocks until that card's click decides."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from iris.ui.chat.run_visibility import card_from_control_result, insert_visibility_card
from iris.ui.chat.shell_approval import ApprovalState, preview_command, should_auto_run
from iris.ui.chat.shell_controller import bind_block, get_by_request, new_request

# Chat attr: request_id → block_id (HF-05 — not FIFO pop(0) identity).
SHELL_CONFIRM_MAP_ATTR = "_shell_confirm_by_request"
# Legacy list attr — readers may exist; writers no longer use it as identity.
SHELL_CONFIRM_BLOCK_ATTR = "_shell_confirm_block_ids"
DEFAULT_APPROVAL_WAIT_S = 300.0


@dataclass(frozen=True)
class CardConfirmResult:
    """Card gate outcome. approved=None → UI unavailable (fail-closed for shell)."""

    approved: bool | None
    block_id: str = ""


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


def take(block_id: str, timeout: float | None = DEFAULT_APPROVAL_WAIT_S) -> str:
    """Wait for a card decision. Always bounded — expire → deny (empty/"timeout")."""
    with _lock:
        slot = _waits.get(block_id)
    if slot is None:
        # Nothing was armed. Waiting here would leave the worker blocked.
        return ""
    wait_s = DEFAULT_APPROVAL_WAIT_S if timeout is None else max(0.05, float(timeout))
    fired = bool(slot.event.wait(timeout=wait_s))
    with _lock:
        if _waits.get(block_id) is slot:
            _waits.pop(block_id, None)
    if not fired:
        return "timeout"
    return slot.decision


def stash_shell_confirm_block(
    chat: Any | None,
    block_id: str,
    command: str = "",
    *,
    request_id: str = "",
) -> str:
    """Bind request_id↔block_id and stash on chat. Returns request_id used."""
    bid = (block_id or "").strip()
    cmd = str(command or "").strip()
    rid = str(request_id or "").strip()
    if rid:
        existing = get_by_request(rid)
        if existing is None:
            new_request(request_id=rid, command=cmd, block_id=bid)
        else:
            if cmd and not existing.command:
                existing.command = cmd
            if bid:
                bind_block(rid, bid)
    else:
        req = new_request(command=cmd, block_id=bid)
        rid = req.request_id
        if bid:
            bind_block(rid, bid)
    if chat is None or not rid:
        return rid
    m = getattr(chat, SHELL_CONFIRM_MAP_ATTR, None)
    if not isinstance(m, dict):
        m = {}
        setattr(chat, SHELL_CONFIRM_MAP_ATTR, m)
    m[rid] = bid
    return rid


def take_shell_confirm_block(
    chat: Any | None,
    command: str = "",
    *,
    request_id: str = "",
) -> str:
    """Resolve block_id via request_id map (or command match). Never FIFO-only."""
    if chat is None:
        return ""
    rid = str(request_id or "").strip()
    cmd = str(command or "").strip()
    m = getattr(chat, SHELL_CONFIRM_MAP_ATTR, None)
    if not isinstance(m, dict) or not m:
        return ""
    if rid and rid in m:
        return str(m.pop(rid) or "").strip()
    if cmd:
        for key, bid in list(m.items()):
            req = get_by_request(key)
            if req is not None and str(req.command or "").strip() == cmd:
                m.pop(key, None)
                return str(bid or "").strip()
    return ""


def _raise_attention(window: Any) -> None:
    """Bring a Qt window forward so pending Run/Skip is visible."""
    if window is None:
        return
    show_normal = getattr(window, "showNormal", None)
    if callable(show_normal):
        show_normal()
    raise_ = getattr(window, "raise_", None)
    if callable(raise_):
        raise_()
    activate = getattr(window, "activateWindow", None)
    if callable(activate):
        activate()


def try_card_confirm(
    *,
    chat: Any | None,
    command: str,
    title: str,
    approval: ApprovalState,
    wait: Callable[[str], str],
    on_ui: Callable[[Callable[[], Any]], Any] | None = None,
    on_attention: Callable[[], None] | None = None,
) -> CardConfirmResult:
    """채팅 pending 카드로 승인.

    True/False는 승인·거절. insert 불가·실패만 approved=None
    (shell/project/process는 HUD 폴백 금지 — approval_ui_unavailable).
    block_id is set when a pending card was inserted (empty on auto_run).
    """
    can_insert = chat is not None and callable(getattr(chat, "insert_tool_block", None))
    if not can_insert:
        return CardConfirmResult(None)
    if should_auto_run(approval, command):
        return CardConfirmResult(True)

    def _ui(fn: Callable[[], Any]) -> Any:
        if on_ui is None:
            return fn()
        return on_ui(fn)

    def _post() -> str:
        block_id = str(
            chat.insert_tool_block(
                title=title,
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
        return CardConfirmResult(None)
    if on_attention is not None:
        try:
            _ui(on_attention)
        except Exception:
            pass
    decision = wait(block_id)
    approved = decision in ("run", "always")
    return CardConfirmResult(approved, block_id)


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
    on_attention: Callable[[], None] | None = None,
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
    if should_auto_run(approval, command):
        return _run()
    # U06: UI thread / missing card → fail-closed (never silent auto-run).
    if on_ui_thread or not can_insert:
        return {
            "ok": False,
            "action": "project.run",
            "error": "approval_ui_unavailable",
            "result": {
                "approval_required": True,
                "approval_ui_unavailable": True,
            },
        }

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
        return {
            "ok": False,
            "action": "project.run",
            "error": "approval_ui_unavailable",
            "result": {
                "approval_required": True,
                "approval_ui_unavailable": True,
            },
        }
    if on_attention is not None:
        try:
            _ui(on_attention)
        except Exception:
            pass
    if wait(block_id) not in ("run", "always"):
        return _skipped()
    return _run(block_id)
