"""워크스페이스와 캘린더 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import WorkspaceHost

def register_workspace_actions(window: WorkspaceHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        HandlerFn,
        _emulator_running,
        _log,
        err_result,
        ok_result,
    )

    def ws_assistant(_a: dict[str, Any]) -> dict[str, Any]:
        window._show_assistant_workspace()
        _log(window, "workspace.open_assistant", True)
        return ok_result("workspace.open_assistant", {"workspace_mode": window._workspace_mode})

    def ws_obsidian(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_obsidian_icon()
        _log(window, "workspace.open_obsidian", True)
        return ok_result("workspace.open_obsidian", {"workspace_mode": window._workspace_mode})

    def ws_email(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_email_icon()
        _log(window, "workspace.open_email", True)
        return ok_result("workspace.open_email", {"workspace_mode": window._workspace_mode})

    def ws_calendar(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_calendar_icon()
        _log(window, "workspace.open_calendar", True)
        return ok_result("workspace.open_calendar", {"workspace_mode": window._workspace_mode})

    def ws_mobile(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_mobile_icon()
        _log(window, "workspace.open_mobile", True)
        return ok_result(
            "workspace.open_mobile",
            {"emulator_running": _emulator_running()},
        )

    def ws_stub(name: str) -> HandlerFn:
        def _h(_a: dict[str, Any]) -> dict[str, Any]:
            return err_result(name, "not implemented in Iris UI yet (준비 중)")

        return _h

    def cal_list(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import events_as_dicts, list_events

        events = list_events(window._db)
        return ok_result("calendar.list_events", {"events": events_as_dicts(events)})

    def cal_add(a: dict[str, Any]) -> dict[str, Any]:
        from iris.infrastructure.calendar_agent import normalize_start_at
        from iris.storage.calendar_events import add_event, events_as_dicts

        title = str(a.get("title") or "").strip()
        start = str(a.get("start_at") or "").strip()
        if not title or not start:
            return err_result("calendar.add_event", "title and start_at required")
        end_raw = str(a.get("end_at") or "").strip()
        try:
            ev = add_event(
                window._db,
                title=title,
                start_at=normalize_start_at(start),
                end_at=normalize_start_at(end_raw) if end_raw else "",
                note=str(a.get("note") or "").strip(),
                place=str(a.get("place") or "").strip(),
            )
        except Exception as exc:
            return err_result("calendar.add_event", str(exc))
        window._sync_calendar_wiki()
        if getattr(window, "_workspace_mode", "") == "calendar":
            window._reload_calendar_month()
        return ok_result("calendar.add_event", {"event": events_as_dicts([ev])[0]})

    def cal_delete(a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import delete_event

        try:
            eid = int(a.get("id"))
        except (TypeError, ValueError):
            return err_result("calendar.delete_event", "id required")
        ok = delete_event(window._db, eid)
        if ok:
            window._sync_calendar_wiki()
            if getattr(window, "_workspace_mode", "") == "calendar":
                window._reload_calendar_month()
        return ok_result("calendar.delete_event", {"deleted": ok, "id": eid})

    def cal_select_day(a: dict[str, Any]) -> dict[str, Any]:
        day = str(a.get("date") or a.get("day") or "").strip()
        if not day:
            return err_result("calendar.select_day", "date (YYYY-MM-DD) required")
        try:
            if getattr(window, "_workspace_mode", "") != "calendar":
                window._on_calendar_icon()
            selected = window._calendar_page.select_day_iso(day)
            window._reload_calendar_month()
        except Exception as exc:
            return err_result("calendar.select_day", str(exc))
        return ok_result(
            "calendar.select_day",
            {
                "date": selected.isoformat(),
                "year": window._calendar_page.year,
                "month": window._calendar_page.month,
            },
        )

    def cal_set_month(a: dict[str, Any]) -> dict[str, Any]:
        try:
            year = int(a.get("year"))
            month = int(a.get("month"))
        except (TypeError, ValueError):
            return err_result("calendar.set_month", "year and month required")
        try:
            if getattr(window, "_workspace_mode", "") != "calendar":
                window._on_calendar_icon()
            window._calendar_page.set_month(year, month)
            window._reload_calendar_month()
            window._refresh_calendar_holidays()
        except Exception as exc:
            return err_result("calendar.set_month", str(exc))
        return ok_result(
            "calendar.set_month",
            {"year": window._calendar_page.year, "month": window._calendar_page.month},
        )

    def cal_refresh_holidays(_a: dict[str, Any]) -> dict[str, Any]:
        if getattr(window, "_workspace_mode", "") != "calendar":
            window._on_calendar_icon()
        window._refresh_calendar_holidays()
        return ok_result(
            "calendar.refresh_holidays",
            {
                "year": window._calendar_page.year,
                "key_configured": bool(window._settings.data_go_kr_service_key),
            },
        )

    def cal_status(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import events_as_dicts, list_events

        page = getattr(window, "_calendar_page", None)
        events = list_events(window._db)
        return ok_result(
            "calendar.status",
            {
                "workspace_mode": getattr(window, "_workspace_mode", ""),
                "year": getattr(page, "year", None),
                "month": getattr(page, "month", None),
                "selected_day": (
                    page.selected_day.isoformat() if page is not None else ""
                ),
                "event_count": len(events),
                "events": events_as_dicts(events[:30]),
                "holiday_api_key": bool(window._settings.data_go_kr_service_key),
            },
        )

    reg.register(
        "workspace.open_assistant",
        ws_assistant,
        summary="Open assistant / home workspace (orb + chat)",
    )

    reg.register(
        "workspace.open_obsidian",
        ws_obsidian,
        summary="Open Iris Wiki / Obsidian workspace",
    )

    reg.register(
        "workspace.open_email",
        ws_email,
        summary="Open email workspace inbox",
    )

    reg.register(
        "workspace.open_calendar",
        ws_calendar,
        summary="Open calendar workspace (KR holidays + schedule)",
    )

    reg.register(
        "workspace.open_mobile",
        ws_mobile,
        summary="Launch Android emulator (mobile icon)",
    )

    reg.register("calendar.list_events", cal_list, summary="List calendar events")

    reg.register(
        "calendar.add_event",
        cal_add,
        summary="Add calendar event (title, start_at, optional end_at/note/place)",
        risk="medium",
    )

    reg.register(
        "calendar.delete_event",
        cal_delete,
        summary="Delete calendar event by id",
        risk="medium",
    )

    reg.register(
        "calendar.select_day",
        cal_select_day,
        summary="Open calendar and select a day (date=YYYY-MM-DD)",
    )

    reg.register(
        "calendar.set_month",
        cal_set_month,
        summary="Open calendar and show year/month",
    )

    reg.register(
        "calendar.refresh_holidays",
        cal_refresh_holidays,
        summary="Refresh KR public holidays for current calendar year",
    )

    reg.register(
        "calendar.status",
        cal_status,
        summary="Calendar workspace status + upcoming events summary",
    )

    for stub_id, label in (
        ("workspace.open_instagram", "Instagram"),
        ("workspace.open_discord", "Discord"),
        ("workspace.open_kakao", "KakaoTalk"),
        ("workspace.open_telegram", "Telegram"),
    ):
        reg.register(stub_id, ws_stub(stub_id), summary=f"{label} workspace (준비 중)", risk="low")
