"""학습 워크플로 컨트롤 액션."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import LearningHost

def _skill_params(mgr: Any, workflow_id: int) -> list[dict[str, str]]:
    """실행할 때 바꿔 넣을 칸 — learning.run 의 params 키."""
    skill = mgr.workflow_skill(workflow_id) if hasattr(mgr, "workflow_skill") else None
    if skill is None:
        return []
    return [{"name": p.name, "label": p.label, "example": p.example} for p in skill.params]


def register_learning_actions(window: LearningHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _log,
        err_result,
        ok_result,
        policy_for,
    )

    def skill_list(_args: dict[str, Any]) -> dict[str, Any]:
        from iris.ui.chat.skill_mcp_dialogs import list_iris_agent_skills

        return ok_result("skill.list", {"skills": [
            {"name": name, "description": description} for name, description, _path in list_iris_agent_skills()
        ]})

    def skill_view(args: dict[str, Any]) -> dict[str, Any]:
        from pathlib import Path, PureWindowsPath

        from iris.runtime.attachment_context import _is_link
        from iris.system.execution_policy import check_path_allowed, format_tool_payload_for_model
        from iris.ui.chat.skill_mcp_dialogs import list_iris_agent_skills

        name = str(args.get("name") or "").strip()
        catalog = {key: path for key, _description, path in list_iris_agent_skills()}
        selected = catalog.get(name)
        if selected is None:
            return err_result("skill.view", "registered skill not found")
        resource = str(args.get("resource") or "SKILL.md").replace("\\", "/")
        relative = Path(resource)
        if (relative.is_absolute() or PureWindowsPath(resource).drive
                or any(part in ("", ".", "..") for part in resource.split("/")) or ":" in resource):
            return err_result("skill.view", "skill-relative resource required")
        directory = selected.parent
        current = directory
        for part in relative.parts:
            current /= part
            if _is_link(current):
                return err_result("skill.view", "linked skill resources are unavailable")
        if not check_path_allowed(directory, current).allowed or current.suffix.lower() not in {".md", ".txt", ".py", ".json", ".yaml", ".yml"}:
            return err_result("skill.view", "resource is outside the readable skill scope")
        try:
            with current.open(encoding="utf-8") as stream:
                contents = stream.read(20_001)
        except (OSError, UnicodeError):
            return err_result("skill.view", "skill text resource unavailable")
        return ok_result("skill.view", {"name": name, "resource": resource,
                                       "text": format_tool_payload_for_model(contents[:20_000]),
                                       "truncated": len(contents) > 20_000})

    def skill_manage(args: dict[str, Any]) -> dict[str, Any]:
        from iris.ui.chat.skill_mcp_dialogs import manage_iris_agent_skill

        operation, name = str(args.get("operation") or ""), str(args.get("name") or "")
        try:
            return ok_result("skill.manage", manage_iris_agent_skill(operation, name, str(args.get("text") or "")))
        except (OSError, ValueError) as exc:
            return err_result("skill.manage", str(exc) if isinstance(exc, ValueError) else "skill update failed")

    def learning_list(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.list", "learning manager unavailable")
        enabled_only = bool(_a.get("enabled_only", False))
        items = []
        for wf in mgr.list_learned_workflows(enabled_only=enabled_only):
            items.append(
                {
                    "id": wf.id,
                    "trace_id": wf.trace_id,
                    "name": wf.name,
                    "summary": wf.summary,
                    "status": wf.status,
                    "primary_apps": wf.primary_apps,
                    "run_count": wf.run_count,
                    "enabled": bool(wf.enabled),
                    "trace_path": wf.trace_path,
                    "params": _skill_params(mgr, wf.id),
                }
            )
        return ok_result("learning.list", {"workflows": items})

    def learning_get(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.get", "learning manager unavailable")
        wid = args.get("id") or args.get("workflow_id")
        if wid is None:
            return err_result("learning.get", "id required")
        wf = mgr.get_learned_workflow(int(wid))
        if wf is None:
            return err_result("learning.get", f"workflow {wid} not found")
        return ok_result(
            "learning.get",
            {
                "id": wf.id,
                "trace_id": wf.trace_id,
                "name": wf.name,
                "summary": wf.summary,
                "status": wf.status,
                "primary_apps": wf.primary_apps,
                "run_count": wf.run_count,
                "enabled": bool(wf.enabled),
                "trace_path": wf.trace_path,
                "source_session_id": wf.source_session_id,
            },
        )

    def learning_run(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.run", "learning manager unavailable")
        task = str(args.get("task") or "").strip()
        wid = args.get("id") or args.get("workflow_id")
        trace_id = str(args.get("trace_id") or "").strip()
        raw_params = args.get("params") or {}
        params = (
            {str(k): str(v) for k, v in raw_params.items()} if isinstance(raw_params, dict) else {}
        )
        try:
            if wid is not None:
                run = mgr.run_learned_workflow(int(wid), task, params)
            elif trace_id:
                run = mgr.execute_workflow(trace_id, task, params)
            else:
                return err_result("learning.run", "id or trace_id required")
        except Exception as exc:
            return err_result("learning.run", str(exc)[:300])
        return ok_result(
            "learning.run",
            {
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "trace_id": run.trace_id,
                "task": run.task,
                "status": run.status,
                "message": run.message,
            },
        )

    def learning_run_status(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.run_status", "learning manager unavailable")
        run_id = str(args.get("run_id") or "").strip()
        if not run_id:
            return err_result("learning.run_status", "run_id required")
        run = mgr.get_workflow_run_status(run_id)
        if run is None:
            return err_result("learning.run_status", f"run {run_id} not found")
        return ok_result(
            "learning.run_status",
            {
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "trace_id": run.trace_id,
                "task": run.task,
                "status": run.status,
                "message": run.message,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            },
        )

    def learning_status(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.status", "learning manager unavailable")
        return ok_result(
            "learning.status",
            {
                "state": getattr(mgr.state, "value", str(mgr.state)),
                "session_id": mgr.session_id,
                "last_error": mgr.last_error,
            },
        )

    def learning_start(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.start", "learning manager unavailable")
        from iris.learning.models import LearningState
        if mgr.state != LearningState.IDLE:
            return err_result("learning.start", f"cannot start: state={mgr.state.value}")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, window._start_learning_session)
        return ok_result("learning.start", {"message": "학습 세션 시작 중…"})

    def learning_stop(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.stop", "learning manager unavailable")
        from iris.learning.models import LearningState
        if mgr.state != LearningState.RECORDING:
            return err_result("learning.stop", f"cannot stop: state={mgr.state.value}")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, window._stop_learning_session)
        return ok_result("learning.stop", {"message": "학습 녹화 종료 중…"})

    def learning_toggle(_a: dict[str, Any]) -> dict[str, Any]:
        """타이틀바 학습 아이콘과 동일 — IDLE↔RECORDING 토글."""
        from iris.learning.models import LearningState

        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.toggle", "learning manager unavailable")
        before = getattr(mgr.state, "value", str(mgr.state))
        window._on_learning_toggle()
        after = getattr(mgr.state, "value", str(mgr.state))
        _log(window, "learning.toggle", True)
        return ok_result(
            "learning.toggle",
            {"was": before, "state": after, "idle": mgr.state == LearningState.IDLE},
        )

    reg.register("skill.list", skill_list, summary="List installed IRIS skills")
    reg.register("skill.view", skill_view, summary="Read a registered skill and its text resources")
    reg.register("skill.manage", skill_manage, summary="Change a registered skill as requested (use operation and name)",
                 risk="high", confirm_required=True)
    reg.register(
        "learning.list",
        learning_list,
        summary="List learned computer-use workflows",
        risk="low",
    )

    reg.register(
        "learning.get",
        learning_get,
        summary="Get learned workflow details",
        risk="low",
    )

    reg.register(
        "learning.run",
        learning_run,
        summary=(
            "Run a learned skill on screen (moves mouse/keyboard). "
            "args: id, params={name: value} from learning.list"
        ),
        risk="high",
        confirm_required=not policy_for(
            getattr(getattr(window, "_learning_prefs", None), "permission_level", "normal")
        ).allow_unrestricted_os_control,
    )

    reg.register(
        "learning.run_status",
        learning_run_status,
        summary="Get learned workflow run status",
        risk="low",
    )

    reg.register(
        "learning.status",
        learning_status,
        summary="Current learning recorder state",
        risk="low",
    )

    reg.register(
        "learning.start",
        learning_start,
        summary="Start demonstration recording session",
        risk="medium",
    )

    reg.register(
        "learning.stop",
        learning_stop,
        summary="Stop recording and process learned workflow",
        risk="medium",
    )

    reg.register(
        "learning.toggle",
        learning_toggle,
        summary="Toggle learning record (same as titlebar learning icon)",
        risk="medium",
    )
