"""App Host demo and directory control actions."""

from __future__ import annotations

from typing import Any

from iris.apps.directory import AppDirectory, entries_as_dicts
from iris.engine.app_ui import app_ui_from_tool_meta
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.hosts import ChatHost


_DEMO_RESOURCE = "app_host_ping.html"
_DEMO_TITLE = "데모 앱"


def register_app_actions(window: ChatHost, reg: ActionRegistry) -> None:
    # Circular: control_bindings imports register_app_actions.
    from iris.ui.control_bindings import _log, err_result, ok_result

    def app_demo_ping(_args: dict[str, Any]) -> dict[str, Any]:
        offer = app_ui_from_tool_meta(
            {"ui": {"resourceUri": _DEMO_RESOURCE}},
            default_title=_DEMO_TITLE,
        )
        if offer is None:
            return err_result("app.demo_ping", "demo fixture missing")
        chat = getattr(window, "_chat", None)
        show = getattr(chat, "show_app_host", None) if chat is not None else None
        shown = False
        if callable(show):
            shown = bool(show(offer.html_path, title=offer.title))
        _log(window, "app.demo_ping", True)
        return ok_result(
            "app.demo_ping",
            {
                "ok": True,
                "shown": shown,
                "title": offer.title,
                "html_path": offer.html_path,
                "_meta": {"ui": {"resourceUri": _DEMO_RESOURCE}},
            },
        )

    def app_directory_list(args: dict[str, Any]) -> dict[str, Any]:
        query = str((args or {}).get("query") or "").strip()
        directory = AppDirectory()
        entries = directory.search(query) if query else directory.list()
        _log(window, "app.directory_list", True)
        return ok_result(
            "app.directory_list",
            {
                "ok": True,
                "apps": entries_as_dicts(entries),
                "query": query,
            },
        )

    reg.register(
        "app.demo_ping",
        app_demo_ping,
        summary="Open the App Host demo (app_host_ping.html)",
        risk="low",
    )
    reg.register(
        "app.directory_list",
        app_directory_list,
        summary="List or search App Host directory apps",
        risk="low",
    )
