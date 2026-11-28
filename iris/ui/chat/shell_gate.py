"""One wait per shell card. The worker blocks until that card's click decides."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from iris.ui.chat.run_visibility import card_from_control_result, insert_visibility_card
from iris.ui.chat.shell_approval import ApprovalState, preview_command, should_auto_run
from iris.ui.chat.shell_controller import bind_block, get_by_request, new_request

_log = logging.getLogger(__name__)

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
        if slot is None or slot.event.is_set():
            return
        slot.decision = decision
        slot.event.set()


def cancel_pending_approvals() -> None:
    """Wake undecided approval waiters when the product window closes."""
    with _lock:
        for slot in _waits.values():
            if not slot.event.is_set():
                slot.decision = "skip"
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
    """Resolve block_id via request_id only (FPR-03 — no command-string fallback).

    ``command`` is accepted for call-site compatibility but never used to bind
    a Shell Box; same command in another request must not steal this block.
    """
    if chat is None:
        return ""
    rid = str(request_id or "").strip()
    # command ignored — FPR-03 binds Shell Box by request_id only
    m = getattr(chat, SHELL_CONFIRM_MAP_ATTR, None)
    if not isinstance(m, dict) or not m:
        return ""
    if rid and rid in m:
        return str(m.pop(rid) or "").strip()
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


def _insert_pending_shell_box(
    chat: Any,
    *,
    title: str,
    command: str,
    on_ui: Callable[[Callable[[], Any]], Any] | None,
    arm_wait: bool,
    allow_always: bool = True,
) -> str:
    """Insert a pending Shell Box. arm_wait=True only for manual Run/Skip."""

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
                allow_always=allow_always,
            )
            or ""
        ).strip()
        if block_id and arm_wait:
            arm(block_id)
        return block_id

    try:
        return str(_ui(_post) or "").strip()
    except Exception:
        _log.exception("shell_gate insert-fail title=%s command=%r", title, command)
        return ""


def try_card_confirm(
    *,
    chat: Any | None,
    command: str,
    title: str,
    approval: ApprovalState,
    wait: Callable[[str], str],
    on_ui: Callable[[Callable[[], Any]], Any] | None = None,
    on_attention: Callable[[], None] | None = None,
    allow_auto: bool = True,
    allow_always: bool | None = None,
) -> CardConfirmResult:
    """채팅 pending 카드로 승인.

    True/False는 승인·거절. insert 불가·실패만 approved=None
    (shell/project/process는 HUD 폴백 금지 — approval_ui_unavailable).
    Auto-run still inserts a Shell Box (skips wait only). block_id set when
    insert succeeded; empty block_id on auto means insert failed but run may continue.
    allow_auto=False: EXTERNAL_EFFECT / SENSITIVE — Run Everything never skips the card.
    allow_always=False: hide Always Allow (defaults to allow_auto when omitted).
    """
    show_always = allow_auto if allow_always is None else bool(allow_always)
    can_insert = chat is not None and callable(getattr(chat, "insert_tool_block", None))
    if not can_insert:
        return CardConfirmResult(None)
    if allow_auto and should_auto_run(approval, command):
        # FPR-01: Box always; approval wait skipped. Insert miss → log, still approve.
        block_id = _insert_pending_shell_box(
            chat,
            title=title,
            command=command,
            on_ui=on_ui,
            arm_wait=False,
            allow_always=show_always,
        )
        if not block_id:
            _log.error(
                "shell_gate auto-run insert-miss title=%s command=%r",
                title,
                command,
            )
        return CardConfirmResult(True, block_id)

    def _ui(fn: Callable[[], Any]) -> Any:
        if on_ui is None:
            return fn()
        return on_ui(fn)

    block_id = _insert_pending_shell_box(
        chat,
        title=title,
        command=command,
        on_ui=on_ui,
        arm_wait=True,
        allow_always=show_always,
    )
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
                _log.exception(
                    "shell_gate paint-fail block_id=%s title=%s",
                    block_id,
                    getattr(card, "title", ""),
                )
    try:
        insert_visibility_card(chat, card)
    except Exception:
        _log.exception(
            "shell_gate insert-fail (visibility) title=%s",
            getattr(card, "title", ""),
        )


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
                _log.exception("shell_gate paint-ui-fail command=%r", command)
        return result if isinstance(result, dict) else envelope

    def _run(block_id: str = "") -> dict:
        return _finish(action(payload), block_id)

    can_insert = chat is not None and callable(getattr(chat, "insert_tool_block", None))
    if should_auto_run(approval, command):
        # FPR-01: Box shown immediately; wait skipped. Miss → log, still run.
        block_id = ""
        if can_insert:
            block_id = _insert_pending_shell_box(
                chat,
                title="Shell",
                command=command,
                on_ui=on_ui,
                arm_wait=False,
            )
            if not block_id:
                _log.error(
                    "shell_gate project auto-run insert-miss command=%r", command
                )
        return _run(block_id)
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

    block_id = _insert_pending_shell_box(
        chat,
        title="Shell",
        command=command,
        on_ui=on_ui,
        arm_wait=True,
    )
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
