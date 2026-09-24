"""ping / catalog / state 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
    ControlSurface,
)
from iris.ui.control_actions.hosts import SessionHost

def register_session_actions(window: SessionHost, reg: ActionRegistry, surface: ControlSurface) -> None:
    from iris.ui.control_bindings import (
        _emulator_running,
        _emulator_state_fields,
        _iris_ide_context,
        _mic_state_fields,
        _profile_parents,
        load_email_accounts,
        load_user_profile,
        ok_result,
    )

    def ping(_args: dict[str, Any]) -> dict[str, Any]:
        return ok_result("ping", {"alive": True, "booting": surface.booting})

    def get_catalog(_args: dict[str, Any]) -> dict[str, Any]:
        return ok_result("get_catalog", {"actions": reg.catalog()})

    def get_state(_args: dict[str, Any]) -> dict[str, Any]:
        profile = load_user_profile(window._db)
        session = window._get_bound_ide_session(refresh=True)
        accounts = [
            {"id": a.id, "address": a.address, "label": a.label}
            for a in load_email_accounts(window._db)
        ]
        return ok_result(
            "get_state",
            {
                "booting": surface.booting,
                "ui_mode": window._ui_mode,
                "workspace_mode": window._workspace_mode,
                "preferred_ide": profile.preferred_ide,
                "project_root": profile.project_root,
                "project_parents": [str(p) for p in _profile_parents(window)],
                "ide_attached": bool(session),
                "ide_pid": session.pid if session else None,
                "ide_session": (
                    {
                        "active": session.active,
                        "ide_id": session.ide_id,
                        "hwnd": session.hwnd,
                        "pid": session.pid,
                        "workspace_root": session.workspace_root,
                        "mode": session.mode,
                        "source": session.source,
                        "last_seen_at": session.last_seen_at,
                    }
                    if session
                    else {
                        "active": False,
                        "ide_id": "",
                        "hwnd": None,
                        "pid": None,
                        "workspace_root": "",
                        "mode": "welcome",
                        "source": "",
                        "last_seen_at": 0.0,
                    }
                ),
                "hermes_online": bool(getattr(window, "_hermes_online", False)),
                "hermes_enabled": bool(window._settings.hermes_enabled),
                "model": window._settings.model_name or window._settings.ollama_model,
                "email_accounts": accounts,
                "selected_email_account_id": window._selected_email_account_id,
                "calendar": {
                    "year": getattr(getattr(window, "_calendar_page", None), "year", None),
                    "month": getattr(getattr(window, "_calendar_page", None), "month", None),
                    "selected_day": (
                        window._calendar_page.selected_day.isoformat()
                        if getattr(window, "_calendar_page", None) is not None
                        else ""
                    ),
                    "holiday_api_key": bool(
                        getattr(window._settings, "data_go_kr_service_key", "")
                    ),
                },
                "mic": _mic_state_fields(window),
                "emulator_running": _emulator_running(),
                **_emulator_state_fields(),
                **_iris_ide_context(window),
            },
        )

    reg.register("ping", ping, summary="Iris alive check / ping")

    reg.register(
        "get_catalog",
        get_catalog,
        summary="List all Iris control actions (catalog)",
    )

    reg.register(
        "get_state",
        get_state,
        summary="Iris session state: ui_mode companion workspace IDE project_root model",
    )
