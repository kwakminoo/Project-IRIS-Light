"""Iris Shell control action — home-surface scoped commands (chat cell, no console)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.iris_shell import (
    ShellJob,
    ShellOutcome,
    outcome_as_result,
    parse_shell_job,
    stream_shell_job,
)
from iris.ui.chat.shell_gate import take_shell_confirm_block

# Live card output budget (VisibilityCard stays at 400 for project.run summaries).
_MAX_LIVE_OUTPUT = 8192
_PAINT_INTERVAL_S = 0.08


def _ide_companion_active(window: Any) -> bool:
    mode = str(getattr(window, "_ui_mode", "") or "").strip().lower()
    if mode in {"companion", "ide", "ide_companion"}:
        return True
    page = getattr(window, "_companion_page", None)
    if page is not None and bool(getattr(page, "isVisible", lambda: False)()):
        stack = getattr(window, "_body_stack", None)
        if stack is not None and stack.currentWidget() is page:
            return True
    return False


def _clip_live(text: str, limit: int = _MAX_LIVE_OUTPUT) -> str:
    raw = text or ""
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)] + "…"


def run_shell_live(
    *,
    chat: Any | None,
    on_ui: Callable[[Callable[[], Any]], Any],
    job: ShellJob,
    block_id: str = "",
    stream_fn: Callable[..., ShellOutcome] = stream_shell_job,
    title: str = "Iris Shell",
) -> tuple[ShellOutcome, str]:
    """One shell card: running (growing output) → done. Returns (outcome, block_id)."""
    bid = (block_id or "").strip()
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
            return _clip_live("".join(parts))

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

    _paint("running", "", status="ok")
    outcome = stream_fn(job, on_chunk)
    # Final flush always (coalesced mid-stream paints may have been skipped).
    status = "ok" if outcome.ok else "error"
    body = outcome.stdout or ""
    if outcome.stderr and outcome.stderr.strip():
        body = f"{body.rstrip()}\nstderr:\n{outcome.stderr}".strip() if body else outcome.stderr
    meta = (outcome.summary or "").strip()
    if meta:
        body = f"{body.rstrip()}\n{meta}".strip() if body else meta
    _paint("done", _clip_live(body), status=status)
    return outcome, bid


def register_shell_actions(window: Any, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import _call_on_ui

    def iris_shell(args: dict[str, Any]) -> dict[str, Any]:
        if _ide_companion_active(window):
            return err_result(
                "shell.run",
                "IDE Companion에서는 shell.run 대신 SpeakTools project.run을 쓰세요.",
            )
        try:
            job = parse_shell_job(args if isinstance(args, dict) else {})
        except (OSError, ValueError) as exc:
            return err_result("shell.run", str(exc))

        chat = getattr(window, "_chat", None)
        block_id = take_shell_confirm_block(chat)
        outcome, _bid = run_shell_live(
            chat=chat,
            on_ui=lambda fn: _call_on_ui(window, fn),
            job=job,
            block_id=block_id,
        )
        payload = outcome_as_result(outcome)
        if outcome.ok:
            return ok_result("shell.run", payload)
        return err_result("shell.run", outcome.summary or "shell failed", payload)

    # shell.run owns its chat card (pending→running→done). Do not wrap
    # _with_run_visibility — that would insert a second card after confirm.
    reg.register(
        "shell.run",
        iris_shell,
        summary=(
            "Run a shell command on the Iris home surface (no console window; "
            "output appears as an Iris Shell chat card). cwd must be under the user home. "
            "When IDE Companion is active, use project.run instead."
        ),
        risk="high",
        confirm_required=True,
    )
