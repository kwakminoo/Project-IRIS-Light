"""Control action process.manage — headless Execution Runtime path."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_runtime import default_runtime


def register_process_actions(window: Any, reg: ActionRegistry) -> None:
    del window  # headless registry; no Qt host

    def process_manage(args: dict[str, Any]) -> dict[str, Any]:
        out = default_runtime().manage(args)
        if out.get("ok"):
            return ok_result("process.manage", out.get("data") or {})
        return err_result(
            "process.manage",
            str(out.get("error") or "process.manage failed"),
            out.get("data") if isinstance(out.get("data"), dict) else {},
        )

    reg.register(
        "process.manage",
        process_manage,
        summary=(
            "Manage Iris Execution Runtime processes (list|status|read_output|wait|cancel; "
            "optional start / write_stdin stub). Required: action. run_id required except list|start."
        ),
        risk="medium",
        confirm_required=False,
    )
