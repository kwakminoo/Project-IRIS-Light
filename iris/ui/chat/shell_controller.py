"""U07 — Unified Shell Controller (thin registry + one-box live paint).

Maps request_id ↔ block_id ↔ run_id. Runtime remains execution authority.
Shell Box only paints; it does not spawn processes itself.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from iris.system.iris_shell import ShellJob, ShellOutcome, stream_shell_job

# Live card output budget (VisibilityCard stays at 400 for project.run summaries).
# Full stdout/stderr remain on Execution Runtime per-run logs; UI is a ring view.
_MAX_LIVE_OUTPUT = 8192
_LIVE_HEAD_CHARS = 512
_PAINT_INTERVAL_S = 0.08


@dataclass
class ShellRequest:
    request_id: str
    block_id: str = ""
    run_id: str = ""
    session_id: str = ""
    workspace_id: str = ""
    status: str = "awaiting_approval"
    command: str = ""


_lock = threading.RLock()
_by_request: dict[str, ShellRequest] = {}
_by_block: dict[str, str] = {}
_by_run: dict[str, str] = {}


def new_request(
    *,
    session_id: str = "",
    workspace_id: str = "",
    command: str = "",
    block_id: str = "",
    request_id: str | None = None,
) -> ShellRequest:
    rid = str(request_id or "").strip() or uuid.uuid4().hex
    req = ShellRequest(
        request_id=rid,
        block_id=str(block_id or "").strip(),
        session_id=str(session_id or "").strip(),
        workspace_id=str(workspace_id or "").strip(),
        command=str(command or ""),
        status="awaiting_approval",
    )
    with _lock:
        _by_request[rid] = req
        if req.block_id:
            _by_block[req.block_id] = rid
    return req


def bind_block(request_id: str, block_id: str) -> None:
    rid = str(request_id or "").strip()
    bid = str(block_id or "").strip()
    with _lock:
        req = _by_request.get(rid)
        if req is None or not bid:
            return
        old = req.block_id
        if old and old != bid:
            _by_block.pop(old, None)
        req.block_id = bid
        _by_block[bid] = rid


def bind_run(request_id: str, run_id: str) -> None:
    rid = str(request_id or "").strip()
    run = str(run_id or "").strip()
    with _lock:
        req = _by_request.get(rid)
        if req is None or not run:
            return
        old = req.run_id
        if old and old != run:
            _by_run.pop(old, None)
        req.run_id = run
        if req.status in ("awaiting_approval", "approved", "queued", ""):
            req.status = "running"
        _by_run[run] = rid


def set_status(request_id: str, status: str) -> None:
    rid = str(request_id or "").strip()
    with _lock:
        req = _by_request.get(rid)
        if req is None:
            return
        req.status = str(status or req.status)


def get_by_request(request_id: str) -> ShellRequest | None:
    with _lock:
        return _by_request.get(str(request_id or "").strip())


def get_by_block(block_id: str) -> ShellRequest | None:
    with _lock:
        rid = _by_block.get(str(block_id or "").strip())
        return _by_request.get(rid) if rid else None


def get_by_run(run_id: str) -> ShellRequest | None:
    with _lock:
        rid = _by_run.get(str(run_id or "").strip())
        return _by_request.get(rid) if rid else None


def cancel_request(request_id: str) -> bool:
    """Cancel via Runtime when run_id is bound. Same path for Shell Box stop."""
    rid = str(request_id or "").strip()
    with _lock:
        req = _by_request.get(rid)
        run_id = req.run_id if req is not None else ""
    if not rid:
        return False
    if not run_id:
        set_status(rid, "cancelled")
        return False
    from iris.system.execution_runtime import default_runtime

    try:
        default_runtime().cancel(run_id)
    except Exception:
        set_status(rid, "cancelled")
        return False
    set_status(rid, "cancelled")
    return True


def cancel_by_block(block_id: str) -> bool:
    req = get_by_block(block_id)
    if req is None:
        return False
    return cancel_request(req.request_id)


def reset_for_tests() -> None:
    with _lock:
        _by_request.clear()
        _by_block.clear()
        _by_run.clear()


# Lifecycle → Shell Box phase (pending / running / done)
UI_PHASE = {
    "awaiting_approval": "pending",
    "approved": "pending",
    "rejected": "done",
    "queued": "running",
    "running": "running",
    "completed": "done",
    "failed": "done",
    "cancelled": "done",
    "timed_out": "done",
    "interrupted": "done",
}


def ui_phase(status: str) -> str:
    return UI_PHASE.get(str(status or ""), "done")


def clip_live(text: str, limit: int = _MAX_LIVE_OUTPUT) -> str:
    """UI ring clip: keep a short head + newest tail (do not drop only the end)."""
    raw = text or ""
    if len(raw) <= limit:
        return raw
    marker = "\n…[truncated — full log on run record]…\n"
    head = min(_LIVE_HEAD_CHARS, max(0, limit // 4))
    tail = max(0, limit - head - len(marker))
    if tail <= 0:
        return raw[: max(0, limit - 1)] + "…"
    return raw[:head] + marker + raw[-tail:]


def run_shell_live(
    *,
    chat: Any | None,
    on_ui: Callable[[Callable[[], Any]], Any],
    job: ShellJob,
    block_id: str = "",
    stream_fn: Callable[..., ShellOutcome] = stream_shell_job,
    title: str = "Iris Shell",
    request_id: str = "",
) -> tuple[ShellOutcome, str]:
    """One shell card: running (growing output) → done. Returns (outcome, block_id)."""
    bid = (block_id or "").strip()
    rid = str(request_id or "").strip()
    command = job.command
    parts: list[str] = []
    lock = threading.Lock()
    last_paint = 0.0

    def _ui(fn: Callable[[], Any]) -> Any:
        return on_ui(fn)

    def _paint(phase: str, output: str, status: str = "ok") -> None:
        nonlocal bid

        def _do() -> None:
            nonlocal bid
            if chat is None:
                return
            kwargs = {
                "title": title,
                "command": command,
                "output": output,
                "status": status,
                "phase": phase,
            }
            if bid:
                replace = getattr(chat, "replace_tool_block", None)
                if callable(replace) and replace(bid, **kwargs):
                    return
            insert = getattr(chat, "insert_tool_block", None)
            if callable(insert):
                bid = str(insert(**kwargs) or "").strip() or bid

        try:
            _ui(_do)
        except Exception:
            pass

    def _snapshot() -> str:
        with lock:
            return clip_live("".join(parts))

    def _maybe_paint_running() -> None:
        nonlocal last_paint
        now = time.monotonic()
        with lock:
            if (now - last_paint) < _PAINT_INTERVAL_S:
                return
            last_paint = now
        _paint("running", _snapshot(), status="ok")

    def on_chunk(chunk: str) -> None:
        with lock:
            parts.append(chunk or "")
        _maybe_paint_running()

    if rid:
        set_status(rid, "running")
        if bid:
            bind_block(rid, bid)
    _paint("running", "", status="ok")
    outcome = stream_fn(job, on_chunk)
    # Final flush always (coalesced mid-stream paints may have been skipped).
    card_status = "ok" if outcome.ok else "error"
    body = outcome.stdout or ""
    if outcome.stderr and outcome.stderr.strip():
        body = f"{body.rstrip()}\nstderr:\n{outcome.stderr}".strip() if body else outcome.stderr
    meta = (outcome.summary or "").strip()
    if meta:
        body = f"{body.rstrip()}\n{meta}".strip() if body else meta
    _paint("done", clip_live(body), status=card_status)
    if rid:
        if bid:
            bind_block(rid, bid)
        if outcome.run_id:
            bind_run(rid, outcome.run_id)
        life = str(outcome.status or "").strip().lower()
        if life in ("cancelled", "timed_out", "interrupted", "failed"):
            set_status(rid, life)
        elif life == "completed" and outcome.ok:
            set_status(rid, "completed")
        else:
            set_status(rid, "completed" if outcome.ok else "failed")
    return outcome, bid
