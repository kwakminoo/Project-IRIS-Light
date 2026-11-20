"""App Host demo and directory control actions."""

from __future__ import annotations

from typing import Any

from iris.apps.directory import AppDirectory, entries_as_dicts
from iris.apps.offer import ephemeral_offer
from iris.engine.app_ui import app_ui_from_tool_meta
from iris.system.control_surface import ActionRegistry
from iris.ui.chat.transcript_app import (
    IncompleteAppHtmlError,
    require_complete_app_html,
)
from iris.ui.control_actions.hosts import ChatHost


_DEMO_RESOURCE = "app_host_ping.html"
_DEMO_TITLE = "데모 앱"
_PRESENT_HTML_SUMMARY = (
    "Present model-authored HTML as an interactive app inline in the chat transcript. "
    "Use for calculators, quizzes, forms, tools the user can operate. "
    "Pass a complete HTML document in html. Do not write Desktop .html files for this."
)
_OPEN_SUMMARY = (
    "Open an installed or builtin App Directory app by app_id "
    "(e.g. demo-ping). Prefer @app / directory for known apps; "
    "use app.present_html for invented UI."
)


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

    def app_present_html(args: dict[str, Any]) -> dict[str, Any]:
        raw = args or {}
        title = str(raw.get("title") or "").strip() or "앱"
        html = raw.get("html")
        html_text = html if isinstance(html, str) else ""
        try:
            html_text = require_complete_app_html(html_text)
            offer = ephemeral_offer(title, html_text)
        except (ValueError, IncompleteAppHtmlError) as exc:
            return err_result("app.present_html", str(exc))
        chat = getattr(window, "_chat", None)
        shown = False
        if chat is not None:
            present = getattr(chat, "present_chat_app_offer", None)
            if callable(present):
                shown = bool(present(offer))
            else:
                show = getattr(chat, "show_app_host", None)
                if callable(show):
                    shown = bool(show(offer.html_path, title=offer.title))
        _log(window, "app.present_html", True)
        return ok_result(
            "app.present_html",
            {
                "ok": True,
                "shown": shown,
                "title": offer.title,
                "html_path": offer.html_path,
                "offer_id": offer.offer_id,
                "kind": "ephemeral",
                "_meta": {"ui": {"resourceUri": offer.html_path}},
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

    def app_open(args: dict[str, Any]) -> dict[str, Any]:
        app_id = str((args or {}).get("app_id") or "").strip()
        if not app_id:
            return err_result("app.open", "app_id required")
        entry = AppDirectory().get(app_id)
        if entry is None:
            return err_result("app.open", f"unknown app_id: {app_id}")
        chat = getattr(window, "_chat", None)
        shown = False
        if chat is not None:
            open_fn = getattr(chat, "_open_directory_app", None)
            if callable(open_fn):
                shown = bool(open_fn(entry))
            else:
                show = getattr(chat, "show_app_host", None)
                if callable(show):
                    offer = app_ui_from_tool_meta(
                        {"ui": {"resourceUri": entry.resource_uri}},
                        default_title=entry.title,
                    )
                    if offer is not None and (offer.html_path or "").strip():
                        shown = bool(
                            show(
                                offer.html_path,
                                title=offer.title,
                                offer_id=entry.id,
                            )
                        )
        _log(window, "app.open", True)
        return ok_result(
            "app.open",
            {
                "ok": True,
                "shown": shown,
                "title": entry.title,
                "resource_uri": entry.resource_uri,
                "app_id": entry.id,
            },
        )

    reg.register(
        "app.demo_ping",
        app_demo_ping,
        summary="Open the App Host demo (app_host_ping.html)",
        risk="low",
    )
    reg.register(
        "app.present_html",
        app_present_html,
        summary=_PRESENT_HTML_SUMMARY,
        risk="low",
    )
    reg.register(
        "app.open",
        app_open,
        summary=_OPEN_SUMMARY,
        risk="low",
    )
    def app_list_presented(_args: dict[str, Any]) -> dict[str, Any]:
        chat = getattr(window, "_chat", None)
        apps: list[dict[str, str]] = []
        active = ""
        if chat is not None and hasattr(chat, "list_chat_app_offers"):
            for offer in chat.list_chat_app_offers():
                apps.append(
                    {
                        "offer_id": str(offer.offer_id or ""),
                        "title": str(offer.title or ""),
                        "kind": str(offer.kind or ""),
                        "html_path": str(offer.html_path or ""),
                    }
                )
            active = str(getattr(chat, "active_chat_app_offer_id", "") or "")
        _log(window, "app.list_presented", True)
        return ok_result(
            "app.list_presented",
            {"ok": True, "apps": apps, "active_offer_id": active},
        )

    reg.register(
        "app.directory_list",
        app_directory_list,
        summary="List or search App Host directory apps",
        risk="low",
    )
    reg.register(
        "app.list_presented",
        app_list_presented,
        summary="List ChatAppOffers currently registered in the chat App Host stack",
        risk="low",
    )
