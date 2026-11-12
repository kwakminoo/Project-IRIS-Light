"""Iris Shell control action — home-surface scoped commands (chat cell, no console)."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.iris_shell import outcome_as_result, parse_shell_job, run_shell_job


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
    from iris.ui.control_bindings import _with_run_visibility

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
        outcome = run_shell_job(job)
        payload = outcome_as_result(outcome)
        if outcome.ok:
            return ok_result("shell.run", payload)
        return err_result("shell.run", outcome.summary or "shell failed", payload)

    reg.register(
        "shell.run",
        _with_run_visibility(window, "shell.run", iris_shell),
        summary=(
            "Run a shell command on the Iris home surface (no console window; "
            "output appears as an Iris Shell chat card). cwd must be under the user home. "
            "When IDE Companion is active, use project.run instead."
        ),
        risk="high",
        confirm_required=True,
    )
