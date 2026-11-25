"""Iris Shell control action — home-surface scoped commands (chat cell, no console)."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.iris_shell import (
    ShellJob,
    ShellOutcome,
    outcome_as_result,
    parse_shell_job,
    stream_shell_job,
)
from iris.ui.chat.shell_controller import (
    bind_block,
    clip_live,
    new_request,
    run_shell_live,
)
from iris.ui.chat.shell_gate import take_shell_confirm_block

# Re-exports for checks / callers that imported from this module.
_clip_live = clip_live


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
        # Trusted Control context — ignore model session_id / workspace_id.
        session_id = str(getattr(window, "_conversation_id", "") or "")
        workspace_id = ""

        req = new_request(
            session_id=session_id,
            workspace_id=workspace_id,
            command=job.command,
            block_id=block_id,
        )
        if block_id:
            bind_block(req.request_id, block_id)

        def _stream(job_: ShellJob, on_chunk: Any) -> ShellOutcome:
            return stream_shell_job(
                job_,
                on_chunk,
                session_id=session_id,
                workspace_id=workspace_id,
                owner="shell.run",  # telemetry label only; ACL uses session_id
            )

        outcome, _bid = run_shell_live(
            chat=chat,
            on_ui=lambda fn: _call_on_ui(window, fn),
            job=job,
            block_id=block_id,
            stream_fn=_stream,
            request_id=req.request_id,
        )
        payload = outcome_as_result(outcome)
        payload["request_id"] = req.request_id
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
