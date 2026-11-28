"""반복 작업(루틴) 컨트롤 액션.

사용자가 "매일 9시에 뉴스 3개 정리해줘" 라고 하면 아이리스가 이 액션들을 불러
루틴으로 등록한다. 할 일은 **사용자가 말한 문장 그대로** `task` 에 담아야 한다 —
미리 요약하거나 액션으로 쪼개면 뉘앙스를 잃는다.
"""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry


def register_routine_actions(window: Any, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import _log, err_result, ok_result

    def _as_dict(r) -> dict[str, Any]:
        return {
            "id": r.id,
            "name": r.name,
            "task": r.task,
            "schedule": r.schedule.describe(),
            "kind": r.kind,
            "time_of_day": r.time_of_day,
            "weekdays": r.weekdays,
            "interval_minutes": r.interval_minutes,
            "at": r.at,
            "deliver": r.deliver,
            "enabled": r.enabled,
            "model": r.model,
            "wake_when_closed": r.wake_when_closed,
            "search": r.search,
            "search_engine": r.search_engine,
            "next_run_at": r.next_run_at,
            "last_run_at": r.last_run_at,
            "last_status": r.last_status,
            "run_count": r.run_count,
            "miss_count": r.miss_count,
        }

    def _resolve(args: dict[str, Any]):
        """id 또는 name 으로 루틴 찾기."""
        from iris.storage.routines import find_routine_by_name, get_routine

        raw_id = args.get("id")
        if raw_id not in (None, "", 0):
            try:
                return get_routine(window._db, int(raw_id))
            except (TypeError, ValueError):
                return None
        name = str(args.get("name") or "").strip()
        return find_routine_by_name(window._db, name) if name else None

    def routine_create(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.routines import create_routine

        task = str(args.get("task") or "").strip()
        if not task:
            return err_result("routine.create", "task required (사용자가 말한 문장 그대로)")
        try:
            routine = create_routine(
                window._db,
                name=str(args.get("name") or "").strip(),
                task=task,
                kind=str(args.get("kind") or "daily"),
                time_of_day=str(args.get("time_of_day") or args.get("time") or "09:00"),
                weekdays=str(args.get("weekdays") or ""),
                interval_minutes=int(args.get("interval_minutes") or 60),
                at=str(args.get("at") or ""),
                deliver=str(args.get("deliver") or ""),
                model=str(args.get("model") or ""),
                wake_when_closed=bool(args.get("wake_when_closed") or False),
                search=str(args.get("search") or ""),
                search_engine=str(args.get("search_engine") or "google_news"),
                source="chat",
            )
        except (ValueError, TypeError) as exc:
            return err_result("routine.create", str(exc)[:200])
        window._sync_iris_wiki(routine=routine, change=f"루틴 등록: {routine.name}")
        _log(window, "routine.create", True)
        return ok_result("routine.create", {"routine": _as_dict(routine)})

    def routine_list(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.routines import list_routines

        items = [_as_dict(r) for r in list_routines(window._db)]
        return ok_result("routine.list", {"routines": items, "count": len(items)})

    def routine_get(args: dict[str, Any]) -> dict[str, Any]:
        routine = _resolve(args)
        if routine is None:
            return err_result("routine.get", "routine not found (id or name)")
        return ok_result("routine.get", {"routine": _as_dict(routine)})

    def routine_update(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.routines import update_routine

        routine = _resolve(args)
        if routine is None:
            return err_result("routine.update", "routine not found (id or name)")
        fields: dict[str, Any] = {}
        for key in (
            "name", "task", "kind", "time_of_day", "weekdays",
            "interval_minutes", "at", "deliver", "enabled",
            "model", "wake_when_closed", "search", "search_engine",
        ):
            if key in args and args[key] is not None:
                fields[key] = args[key]
        if "time" in args and "time_of_day" not in fields:
            fields["time_of_day"] = args["time"]
        if not fields:
            return err_result("routine.update", "바꿀 항목이 없습니다")
        updated = update_routine(window._db, routine.id, **fields)
        if updated is None:
            return err_result("routine.update", "update failed")
        window._sync_iris_wiki(
            routine=updated,
            previous_name=routine.name,
            change=f"루틴 변경: {updated.name} ({', '.join(fields)})",
        )
        _log(window, "routine.update", True)
        return ok_result("routine.update", {"routine": _as_dict(updated)})

    def routine_delete(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.routines import delete_routine

        routine = _resolve(args)
        if routine is None:
            return err_result("routine.delete", "routine not found (id or name)")
        delete_routine(window._db, routine.id)
        window._sync_iris_wiki(removed=routine, change=f"루틴 삭제: {routine.name}")
        _log(window, "routine.delete", True)
        return ok_result("routine.delete", {"id": routine.id, "name": routine.name})

    def routine_run(args: dict[str, Any]) -> dict[str, Any]:
        """예약을 기다리지 않고 지금 한 번 돌린다."""
        routine = _resolve(args)
        if routine is None:
            return err_result("routine.run", "routine not found (id or name)")
        started = window._run_routine_now(routine)
        if not started:
            return err_result("routine.run", "다른 루틴이 실행 중입니다. 잠시 후 다시 시도하세요")
        _log(window, "routine.run", True)
        return ok_result("routine.run", {"id": routine.id, "name": routine.name})

    def routine_manage(args: dict[str, Any]) -> dict[str, Any]:
        """Dispatcher only — forwards to create|list|update|delete|run (no duplicate body)."""
        raw = args if isinstance(args, dict) else {}
        op = str(raw.get("operation") or "").strip().lower()
        forwarded = {k: v for k, v in raw.items() if k != "operation"}
        if op == "create":
            return routine_create(forwarded)
        if op == "list":
            return routine_list(forwarded)
        if op == "update":
            return routine_update(forwarded)
        if op == "delete":
            return routine_delete(forwarded)
        if op == "run":
            return routine_run(forwarded)
        return err_result(
            "routine.manage",
            f"unknown operation: {op or '(empty)'} (create|list|update|delete|run)",
        )

    reg.register(
        "routine.create",
        routine_create,
        summary=(
            "Register a recurring task the user asked for. "
            "task = the user's own sentence, verbatim. "
            "kind=daily|weekly|interval|once, time_of_day=HH:MM, weekdays=mon,fri, "
            "interval_minutes=N, at=ISO datetime (once), "
            "deliver=chat,notify,voice,wiki (default chat,notify), "
            "model=pin a specific model (empty = whatever is selected then), "
            "wake_when_closed=true to run even when Iris is closed. "
            "**search**=a web search query to run BEFORE the model, so the answer "
            "is based on real pages instead of guesses. Set it whenever the task "
            "needs today's facts (news, weather, prices, scores) — without it the "
            "model will invent plausible-looking results. "
            "search_engine=google_news (default) | google | bing | google_finance …"
        ),
        risk="medium",
    )
    reg.register(
        "routine.list", routine_list, summary="List registered routines", risk="low"
    )
    reg.register(
        "routine.get", routine_get, summary="Get one routine by id or name", risk="low"
    )
    reg.register(
        "routine.update",
        routine_update,
        summary=(
            "Change a routine by id or name — schedule, task, deliver, or enabled. "
            "Use enabled=false to pause instead of deleting"
        ),
        risk="medium",
    )
    reg.register(
        "routine.delete",
        routine_delete,
        summary="Delete a routine by id or name",
        risk="high",
    )
    reg.register(
        "routine.run",
        routine_run,
        summary="Run a routine right now without waiting for its schedule",
        risk="medium",
    )
    reg.register(
        "routine.manage",
        routine_manage,
        summary=(
            "Hermes cronjob_manage absorb: operation=create|list|update|delete|run. "
            "Dispatcher only — same handlers as routine.create/list/update/delete/run."
        ),
        risk="medium",
    )
