"""Control action process.manage — headless Execution Runtime path."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_runtime import default_runtime


def _start_preview(args: dict[str, Any]) -> str:
    argv = args.get("argv")
    if isinstance(argv, list) and argv:
        return " ".join(str(x) for x in argv)
    for key in ("shell", "command"):
        text = str(args.get(key) or "").strip()
        if text:
            return text
    return "process.manage start"


def _approve_start_nonblocking(window: Any, args: dict[str, Any]) -> bool:
    """shell.run-class gate without HUD.

    process.manage is off-UI; HUD via ``_call_on_ui_unbounded`` wedges /v1/invoke
    until the client times out. Auto-run / chat card only — never ask_hud.
    """
    from iris.ui.chat.shell_approval import load, should_auto_run
    from iris.ui.chat.shell_gate import take, try_card_confirm
    from iris.ui.control_bindings import _call_on_ui

    preview = _start_preview(args)
    approval = load()
    if should_auto_run(approval, preview):
        return True

    chat = getattr(window, "_chat", None)
    if chat is None or not callable(getattr(chat, "insert_tool_block", None)):
        return False

    decided = try_card_confirm(
        chat=chat,
        command=preview,
        title="Process",
        approval=approval,
        wait=take,
        on_ui=lambda fn: _call_on_ui(window, fn),
        on_attention=None,
    )
    if decided.approved is not None:
        return bool(decided.approved)
    return False


def register_process_actions(window: Any, reg: ActionRegistry) -> None:
    def process_manage(args: dict[str, Any]) -> dict[str, Any]:
        raw = args if isinstance(args, dict) else {}
        action = str(raw.get("action") or "").strip()
        rt = default_runtime()

        if action == "start":
            if not _approve_start_nonblocking(window, raw):
                return err_result(
                    "process.manage",
                    "human confirm required",
                    {"confirm_required": True, "risk": "high"},
                )
            # Already approved this invocation — skip second gate inside manage.
            rt.set_human_confirm(lambda _spec, _a: True)
        else:
            rt.set_human_confirm(None)

        out = rt.manage(raw)
        if out.get("ok"):
            return ok_result("process.manage", out.get("data") or {})
        data = out.get("data") if isinstance(out.get("data"), dict) else {}
        return err_result(
            "process.manage",
            str(out.get("error") or "process.manage failed"),
            data if isinstance(data, dict) else {},
        )

    # risk high for start-capable manage; confirm is dynamic (list/status open).
    reg.register(
        "process.manage",
        process_manage,
        summary=(
            "Manage Iris Execution Runtime Local Subprocess runs "
            "(list|status|read_output|wait|cancel; optional start / write_stdin stub). "
            "Not a sandbox. start requires human confirm (shell.run risk class, no HUD); "
            "cwd under workspace root or home. Required: action. "
            "run_id required except list|start. session_id scopes list/ACL."
        ),
        risk="high",
        confirm_required=False,
    )
