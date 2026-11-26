"""Control action process.manage — headless Execution Runtime path."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_context import (
    execution_context_from_control,
    strip_trust_fields,
)
from iris.ui.control_bindings import trusted_execution_context
from iris.system.execution_runtime import default_runtime
from iris.system.process_start_plan import (
    FinalizeStartFailure,
    FinalizedStartPlan,
    finalize_process_start_plan,
)
from iris.system.request_approval import default_approval_ledger
from iris.ui.chat.shell_controller import (
    bind_block,
    bind_run,
    get_by_request,
    get_by_run,
    new_request,
    set_status,
)


def _insert_process_shell_box(window: Any, preview: str, *, phase: str = "pending") -> str:
    """HF-06: auto-approved process.start still gets a Shell Box."""
    from iris.ui.control_bindings import _call_on_ui

    chat = getattr(window, "_chat", None)
    if chat is None or not callable(getattr(chat, "insert_tool_block", None)):
        return ""

    def _post() -> str:
        return str(
            chat.insert_tool_block(
                title="Process",
                command=preview,
                output="",
                status="ok",
                phase=phase,
            )
            or ""
        ).strip()

    try:
        return str(_call_on_ui(window, _post) or "").strip()
    except Exception:
        return ""


def _approve_start_nonblocking(
    window: Any, preview: str
) -> tuple[bool | None, str]:
    """shell.run-class gate without HUD.

    Returns (approved, block_id). approved=None → approval_ui_unavailable.
    process.manage is off-UI; never ask_hud (HUD wedges /v1/invoke).
    """
    from iris.ui.chat.shell_approval import load, should_auto_run
    from iris.ui.chat.shell_gate import take, try_card_confirm
    from iris.ui.control_bindings import _call_on_ui

    approval = load()
    if should_auto_run(approval, preview):
        return True, _insert_process_shell_box(window, preview, phase="pending")

    chat = getattr(window, "_chat", None)
    if chat is None or not callable(getattr(chat, "insert_tool_block", None)):
        return None, ""

    decided = try_card_confirm(
        chat=chat,
        command=preview,
        title="Process",
        approval=approval,
        wait=take,
        on_ui=lambda fn: _call_on_ui(window, fn),
        on_attention=None,
    )
    if decided.approved is None:
        return None, ""
    return bool(decided.approved), str(decided.block_id or "").strip()


def _trusted_ctx(window: Any) -> Any:
    """Trusted ExecutionContext — prefer turn-frozen snapshot (HF-03)."""
    return trusted_execution_context(window)


def register_process_actions(window: Any, reg: ActionRegistry) -> None:
    def process_manage(args: dict[str, Any]) -> dict[str, Any]:
        raw = strip_trust_fields(args if isinstance(args, dict) else {})
        action = str(raw.get("action") or "").strip()
        rt = default_runtime()
        ctx = _trusted_ctx(window)

        shell_req = None
        if action == "start":
            # Same finalized plan as Runtime.manage consume fingerprint.
            plan = finalize_process_start_plan(
                raw,
                workspace_root=str(ctx.workspace_root or "").strip() or None,
            )
            if isinstance(plan, FinalizeStartFailure):
                return err_result(
                    "process.manage",
                    plan.error,
                    {
                        "error_code": plan.error_code,
                        "hint": plan.hint,
                        **(plan.data if isinstance(plan.data, dict) else {}),
                    },
                )
            assert isinstance(plan, FinalizedStartPlan)
            preview = plan.preview()
            approved, block_id = _approve_start_nonblocking(window, preview)
            if approved is None:
                return err_result(
                    "process.manage",
                    "approval_ui_unavailable",
                    {
                        "confirm_required": True,
                        "risk": "high",
                        "approval_required": True,
                        "approval_ui_unavailable": True,
                    },
                )
            if not approved:
                return err_result(
                    "process.manage",
                    "cancelled",
                    {"confirm_required": True, "risk": "high"},
                )
            # Request-scoped ledger — never set_human_confirm(lambda True).
            fp = plan.fingerprint()
            sid = ctx.effective_session_id()
            if not sid:
                return err_result(
                    "process.manage",
                    "session scope required for approval",
                    {"confirm_required": True, "risk": "high"},
                )
            rec = default_approval_ledger().grant(
                fingerprint=fp,
                session_id=sid,
                workspace_id=str(ctx.workspace_id or ""),
                tool_call_id=str(ctx.tool_call_id or ""),
                block_id=block_id,
            )
            shell_req = new_request(
                request_id=rec.request_id,
                session_id=sid,
                workspace_id=str(ctx.workspace_id or ""),
                command=preview,
                block_id=block_id,
            )
            if block_id:
                bind_block(shell_req.request_id, block_id)
            set_status(shell_req.request_id, "approved")
            ctx = execution_context_from_control(
                session_id=ctx.session_id,
                conversation_id=ctx.conversation_id,
                turn_id=ctx.turn_id,
                tool_call_id=ctx.tool_call_id,
                workspace_id=ctx.workspace_id,
                workspace_root=ctx.workspace_root,
                surface=ctx.surface,
                principal=ctx.principal,
                permission_scope=ctx.permission_scope,
                approval_reference=rec.request_id,
            )
            # HF-04: ledger consume via ctx.approval_reference inside Runtime.manage.
            # Do not mutate rt.set_human_confirm (shared singleton race).

        out = rt.manage(raw, ctx=ctx)
        if out.get("ok"):
            data = out.get("data") or {}
            if shell_req is not None and isinstance(data, dict):
                run_id = str(data.get("run_id") or "").strip()
                if run_id:
                    bind_run(shell_req.request_id, run_id)
                # HF-06: never overwrite cancelled with running.
                cur = get_by_request(shell_req.request_id)
                if cur is None or cur.status != "cancelled":
                    set_status(shell_req.request_id, "running")
                data = {**data, "request_id": shell_req.request_id}
            elif action == "cancel" and isinstance(data, dict):
                rid = str(data.get("run_id") or raw.get("run_id") or "").strip()
                mapped = get_by_run(rid) if rid else None
                if mapped is not None:
                    set_status(mapped.request_id, "cancelled")
            return ok_result("process.manage", data if isinstance(data, dict) else {})
        data = out.get("data") if isinstance(out.get("data"), dict) else {}
        if shell_req is not None:
            set_status(shell_req.request_id, "failed")
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
            "(start|list|status|read_output|wait|cancel). "
            "Not a sandbox. start requires exactly one of argv:list XOR shell:str "
            "(command alias ok) and returns run_id; write_stdin unsupported. "
            "start requires human confirm (shell.run risk class, no HUD); "
            "cwd under trusted workspace root or home. Required: action. "
            "run_id required except list|start. ACL from Control ExecutionContext."
        ),
        risk="high",
        confirm_required=False,
    )
