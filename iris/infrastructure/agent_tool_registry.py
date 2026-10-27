"""Iris Agent native tool registry (Phase 2.5 / §10.1 gate 1).

Product owns the seed catalog. Every seed tool is ``native`` and runs
in-process (no MCP stdio, no Control HTTP on the product speak path).

Speak/chat path: :func:`speak_invoke_agent_tool` (HermesChatWorker).
MCP ``iris_invoke`` for covered seed ``control_action`` values is redirected
via :func:`try_native_control_invoke` (product-path shrink; not plan B rename).
Non-catalog Control actions may still use Control HTTP as **compat only**.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]
CallPath = Literal["native", "mcp_bridge"]

_WIKI_LIST_CAP = 40
_WIKI_SEARCH_CAP = 5
_CAL_LIST_CAP = 200

# Control / MCP short names → product native ids (speak + MCP redirect).
_SPEAK_ALIASES: dict[str, str] = {
    "wiki.list_notes": "iris.wiki.list_notes",
    "wiki.search": "iris.wiki.search",
    "ping": "iris.tools.ping",
    "get_catalog": "iris.tools.catalog",
    "email.list_accounts": "iris.mail.list_accounts",
    "calendar.list_events": "iris.calendar.list_events",
    "get_state": "iris.session.get_state",
    "ide.open_folder": "iris.ide.open_folder",
    "project.open_similar": "iris.project.open_similar",
}


@dataclass(frozen=True)
class IrisToolSpec:
    """One Iris Agent tool. ``name`` is the product id the agent should call."""

    name: str
    summary: str
    domain: str
    call_path: CallPath
    control_action: str = ""


def _ok(tool: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "tool": tool, "call_path": "native"}
    if data:
        out["data"] = data
    return out


def _err(tool: str, message: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "error": message,
        "call_path": "native",
    }
    out.update(extra)
    return out


def _page_notes(notes: list[dict[str, Any]], cap: int) -> dict[str, Any]:
    total = len(notes)
    page = list(notes[:cap])
    return {
        "notes": page,
        "count": len(page),
        "total": total,
        "truncated": total > len(page),
    }


def _live_control_surface() -> Any | None:
    """Iris-process ControlSurface if MainWindow is up; None in MCP child / headless."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return None
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        surface = getattr(widget, "_control_surface", None)
        if surface is not None:
            return surface
    return None


def _invoke_live_control(action: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """In-process Control invoke (no HTTP). None when Iris UI surface is absent."""
    surface = _live_control_surface()
    if surface is None:
        return None
    from iris.system.control_surface import call_registered

    return call_registered(surface, action, dict(args or {}), timeout=30.0)


def _shape_control(tool: str, control_out: dict[str, Any]) -> dict[str, Any]:
    result = control_out.get("result")
    data = dict(result) if isinstance(result, dict) else {}
    data["bridge"] = "none"
    if control_out.get("ok"):
        return _ok(tool, data)
    return _err(
        tool,
        str(control_out.get("error") or "control invoke failed"),
        data=data,
        bridge="none",
    )


def _requires_iris_ui(tool: str) -> dict[str, Any]:
    return _err(
        tool,
        "requires_iris_ui",
        bridge="none",
        hint="Use Iris speak/native path or click Control UI; MCP child has no Qt",
    )


# Seed catalog: product-owned names. Gate 1 CLOSED = zero mcp_bridge rows.
_SEED: tuple[IrisToolSpec, ...] = (
    IrisToolSpec(
        name="iris.tools.ping",
        summary="Iris Agent alive check (native; no MCP)",
        domain="session",
        call_path="native",
        control_action="ping",
    ),
    IrisToolSpec(
        name="iris.tools.catalog",
        summary="List Iris Agent tool catalog (native; no MCP)",
        domain="session",
        call_path="native",
        control_action="get_catalog",
    ),
    IrisToolSpec(
        name="iris.session.get_state",
        summary="Current Iris UI/session state (native; needs Iris UI)",
        domain="session",
        call_path="native",
        control_action="get_state",
    ),
    IrisToolSpec(
        name="iris.wiki.list_notes",
        summary="List Iris Wiki note paths (native; no MCP)",
        domain="wiki",
        call_path="native",
        control_action="wiki.list_notes",
    ),
    IrisToolSpec(
        name="iris.wiki.search",
        summary="Search Iris Wiki notes (native; no MCP)",
        domain="wiki",
        call_path="native",
        control_action="wiki.search",
    ),
    IrisToolSpec(
        name="iris.mail.list_accounts",
        summary="List email accounts (native; no passwords)",
        domain="mail",
        call_path="native",
        control_action="email.list_accounts",
    ),
    IrisToolSpec(
        name="iris.ide.open_folder",
        summary="Open a folder in the IDE Companion (native; needs Iris UI)",
        domain="ide",
        call_path="native",
        control_action="ide.open_folder",
    ),
    IrisToolSpec(
        name="iris.project.open_similar",
        summary="Find and open a similar project folder (native; needs Iris UI)",
        domain="project",
        call_path="native",
        control_action="project.open_similar",
    ),
    IrisToolSpec(
        name="iris.calendar.list_events",
        summary="List calendar events (native; no MCP)",
        domain="calendar",
        call_path="native",
        control_action="calendar.list_events",
    ),
)


class IrisAgentToolRegistry:
    """In-process registry. Native invoke never opens MCP stdio or Control HTTP."""

    def __init__(self) -> None:
        self._specs: dict[str, IrisToolSpec] = {}
        self._handlers: dict[str, HandlerFn] = {}
        for spec in _SEED:
            self._specs[spec.name] = spec
        self._handlers["iris.tools.ping"] = self._handle_ping
        self._handlers["iris.tools.catalog"] = self._handle_catalog
        self._handlers["iris.wiki.list_notes"] = self._handle_wiki_list_notes
        self._handlers["iris.wiki.search"] = self._handle_wiki_search
        self._handlers["iris.mail.list_accounts"] = self._handle_mail_list_accounts
        self._handlers["iris.calendar.list_events"] = self._handle_calendar_list_events
        self._handlers["iris.session.get_state"] = self._handle_session_get_state
        self._handlers["iris.ide.open_folder"] = self._handle_ide_open_folder
        self._handlers["iris.project.open_similar"] = self._handle_project_open_similar

    def _handle_ping(self, _args: dict[str, Any]) -> dict[str, Any]:
        return _ok("iris.tools.ping", {"alive": True, "bridge": "none"})

    def _handle_catalog(self, _args: dict[str, Any]) -> dict[str, Any]:
        return _ok("iris.tools.catalog", {"tools": self.catalog()})

    def _handle_wiki_list_notes(self, args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.iris_wiki import IrisWiki

        try:
            cap = int(args.get("limit") or args.get("cap") or _WIKI_LIST_CAP)
        except (TypeError, ValueError):
            cap = _WIKI_LIST_CAP
        cap = min(80, max(1, cap))
        wiki = IrisWiki()
        notes = [
            {
                "rel_path": n.rel_path,
                "title": n.title,
                "folder": n.folder,
                "source": n.source,
            }
            for n in wiki.list_notes()
        ]
        data = _page_notes(notes, cap)
        data["bridge"] = "none"
        return _ok("iris.wiki.list_notes", data)

    def _handle_wiki_search(self, args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.code_note_prompt import search_code_notes
        from iris.knowledge.iris_wiki import IrisWiki
        from iris.knowledge.wiki_note_index import search_notes, sync_knowledge_notes
        from iris.storage.database import Database

        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            return _err("iris.wiki.search", "query required")
        try:
            limit = int(args.get("limit") or _WIKI_SEARCH_CAP)
        except (TypeError, ValueError):
            limit = _WIKI_SEARCH_CAP
        limit = min(8, max(1, limit))
        wiki = IrisWiki()
        db = Database()
        try:
            sync_knowledge_notes(db, wiki)
            hits = search_notes(db, query, embedder=None, limit=limit)
            code_hits = search_code_notes(wiki._docs.root, query, limit=limit)
        except OSError as exc:
            return _err("iris.wiki.search", str(exc))
        data = {
            "hits": [
                {
                    "rel_path": f"user/{hit.rel_path}",
                    "title": hit.title,
                    "excerpt": hit.excerpt,
                    "score": hit.score,
                    "similarity": hit.similarity,
                    "source": "wiki-note",
                }
                for hit in hits
            ],
            "code_hits": [
                {
                    "rel_path": f"docs/{hit.rel_path}",
                    "title": hit.title,
                    "excerpt": hit.excerpt,
                    "score": hit.score,
                    "source": "code-note",
                }
                for hit in code_hits
            ],
            "count": len(hits),
            "bridge": "none",
        }
        return _ok("iris.wiki.search", data)

    def _handle_mail_list_accounts(self, _args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.database import Database
        from iris.storage.email_accounts import load_email_accounts

        accounts = [
            {"id": a.id, "address": a.address, "label": a.label}
            for a in load_email_accounts(Database())
        ]
        return _ok(
            "iris.mail.list_accounts",
            {"accounts": accounts, "count": len(accounts), "bridge": "none"},
        )

    def _handle_calendar_list_events(self, args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import events_as_dicts, list_events
        from iris.storage.database import Database

        year = args.get("year")
        month = args.get("month")
        try:
            year_i = int(year) if year is not None and str(year).strip() != "" else None
        except (TypeError, ValueError):
            year_i = None
        try:
            month_i = int(month) if month is not None and str(month).strip() != "" else None
        except (TypeError, ValueError):
            month_i = None
        events = list_events(Database(), year=year_i, month=month_i)
        try:
            cap = int(args.get("limit") or _CAL_LIST_CAP)
        except (TypeError, ValueError):
            cap = _CAL_LIST_CAP
        cap = min(500, max(1, cap))
        rows = events_as_dicts(events)
        page = rows[:cap]
        return _ok(
            "iris.calendar.list_events",
            {
                "events": page,
                "count": len(page),
                "total": len(rows),
                "truncated": len(rows) > len(page),
                "bridge": "none",
            },
        )

    def _handle_session_get_state(self, args: dict[str, Any]) -> dict[str, Any]:
        control_out = _invoke_live_control("get_state", args)
        if control_out is None:
            return _requires_iris_ui("iris.session.get_state")
        return _shape_control("iris.session.get_state", control_out)

    def _handle_ide_open_folder(self, args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or "").strip()
        if not path:
            return _err("iris.ide.open_folder", "path required", bridge="none")
        control_out = _invoke_live_control("ide.open_folder", args)
        if control_out is None:
            return _requires_iris_ui("iris.ide.open_folder")
        return _shape_control("iris.ide.open_folder", control_out)

    def _handle_project_open_similar(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or args.get("name") or "").strip()
        if not query:
            return _err(
                "iris.project.open_similar",
                "query required — name a project, or use query like 'iris light'",
                bridge="none",
            )
        control_out = _invoke_live_control("project.open_similar", args)
        if control_out is None:
            return _requires_iris_ui("iris.project.open_similar")
        return _shape_control("iris.project.open_similar", control_out)

    def register(
        self,
        spec: IrisToolSpec,
        handler: HandlerFn | None = None,
    ) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate iris agent tool: {spec.name}")
        if spec.call_path == "native" and handler is None:
            raise ValueError(f"native tool requires handler: {spec.name}")
        self._specs[spec.name] = spec
        if handler is not None:
            self._handlers[spec.name] = handler

    def spec(self, name: str) -> IrisToolSpec | None:
        return self._specs.get(name)

    def catalog(self) -> list[dict[str, Any]]:
        rows = sorted(self._specs.values(), key=lambda s: s.name)
        return [
            {
                "name": s.name,
                "summary": s.summary,
                "domain": s.domain,
                "call_path": s.call_path,
                "control_action": s.control_action,
            }
            for s in rows
        ]

    def native_names(self) -> list[str]:
        return sorted(
            n for n, s in self._specs.items() if s.call_path == "native"
        )

    def invoke(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a native tool in-process. Refuses mcp_bridge (no silent HTTP)."""
        args = dict(args or {})
        spec = self._specs.get(name)
        if spec is None:
            return _err(name, f"unknown tool: {name}")
        if spec.call_path != "native":
            return _err(
                name,
                "mcp_bridge; register a native handler before product use",
                control_action=spec.control_action,
                call_path=spec.call_path,
            )
        handler = self._handlers.get(name)
        if handler is None:
            return _err(name, "native tool missing handler")
        try:
            out = handler(args)
        except Exception as exc:  # noqa: BLE001 — registry boundary
            return _err(name, str(exc) or type(exc).__name__)
        if isinstance(out, dict) and "ok" in out:
            return out
        return _ok(name, out if isinstance(out, dict) else {"result": out})


def default_registry() -> IrisAgentToolRegistry:
    return IrisAgentToolRegistry()


def invoke_agent_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    registry: IrisAgentToolRegistry | None = None,
) -> dict[str, Any]:
    """Documented invoke path for the agent loop (Phase 2.5).

    Native call_path must not open MCP stdio or the Control HTTP surface.
    """
    return (registry or default_registry()).invoke(name, args)


def resolve_speak_tool_name(name: str) -> str:
    key = (name or "").strip()
    return _SPEAK_ALIASES.get(key, key)


def native_tool_for_control_action(
    action: str,
    *,
    registry: IrisAgentToolRegistry | None = None,
) -> str | None:
    """Map a Control/MCP action name to a product native tool id, if covered."""
    key = (action or "").strip()
    if not key:
        return None
    aliased = _SPEAK_ALIASES.get(key)
    if aliased is not None:
        reg = registry or default_registry()
        spec = reg.spec(aliased)
        if spec is not None and spec.call_path == "native":
            return aliased
        return None
    reg = registry or default_registry()
    for row in reg.catalog():
        if row.get("control_action") == key and row.get("call_path") == "native":
            return str(row["name"])
    return None


def try_native_control_invoke(
    action: str,
    args: dict[str, Any] | None = None,
    *,
    registry: IrisAgentToolRegistry | None = None,
) -> dict[str, Any] | None:
    """If ``action`` is already native, invoke in-process and shape Control result.

    Used by MCP ``iris_invoke`` to shrink the Control HTTP product path for
    seed tools. Returns ``None`` when the action is not a native seed mapping
    (compat HTTP may still apply for non-seed Control actions).
    """
    native = native_tool_for_control_action(action, registry=registry)
    if native is None:
        return None
    out = invoke_agent_tool(native, args, registry=registry)
    return {
        "ok": bool(out.get("ok")),
        "action": (action or "").strip() or native,
        "result": out.get("data") if isinstance(out.get("data"), dict) else {},
        "error": "" if out.get("ok") else str(out.get("error") or "native invoke failed"),
        "call_path": "native",
        "tool": out.get("tool") or native,
        "bridge": "none",
    }


def speak_invoke_agent_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    registry: IrisAgentToolRegistry | None = None,
) -> dict[str, Any]:
    """Speak/chat worker entry for native seed tools (Phase 2.5).

    HermesChatWorker calls this instead of MCP stdio → Control HTTP for
    product-owned seed tools.
    """
    return invoke_agent_tool(
        resolve_speak_tool_name(name),
        args,
        registry=registry,
    )


if __name__ == "__main__":
    reg = default_registry()
    assert all(t["call_path"] == "native" for t in reg.catalog()), reg.catalog()
    assert "iris.tools.ping" in reg.native_names()
    assert "iris.wiki.list_notes" in reg.native_names()
    assert "iris.wiki.search" in reg.native_names()
    assert "iris.mail.list_accounts" in reg.native_names()
    assert "iris.calendar.list_events" in reg.native_names()
    ping = reg.invoke("iris.tools.ping")
    assert ping.get("ok") is True
    assert ping.get("call_path") == "native"
    listed = invoke_agent_tool("iris.wiki.list_notes", {"limit": 5}, registry=reg)
    assert listed.get("ok") is True
    assert listed.get("call_path") == "native"
    assert (listed.get("data") or {}).get("bridge") == "none"
    assert "total" in (listed.get("data") or {})
    aliased = speak_invoke_agent_tool("wiki.list_notes", {"limit": 1}, registry=reg)
    assert aliased.get("ok") is True
    assert aliased.get("call_path") == "native"
    searched = speak_invoke_agent_tool(
        "wiki.search", {"query": "iris", "limit": 2}, registry=reg
    )
    assert searched.get("ok") is True
    assert searched.get("call_path") == "native"
    assert (searched.get("data") or {}).get("bridge") == "none"
    assert "hits" in (searched.get("data") or {})
    mail = speak_invoke_agent_tool("email.list_accounts", {}, registry=reg)
    assert mail.get("ok") is True
    assert mail.get("call_path") == "native"
    assert "accounts" in (mail.get("data") or {})
    cal = speak_invoke_agent_tool("calendar.list_events", {"limit": 5}, registry=reg)
    assert cal.get("ok") is True
    assert cal.get("call_path") == "native"
    assert "events" in (cal.get("data") or {})
    redirected = try_native_control_invoke(
        "email.list_accounts", {}, registry=reg
    )
    assert redirected is not None
    assert redirected.get("call_path") == "native"
    assert redirected.get("bridge") == "none"
    ui_needed = reg.invoke("iris.ide.open_folder", {"path": "C:\\\\"})
    assert ui_needed.get("call_path") == "native"
    assert ui_needed.get("ok") is False
    assert ui_needed.get("error") == "requires_iris_ui"
    cat = reg.invoke("iris.tools.catalog")
    assert cat.get("ok") is True
    tools = (cat.get("data") or {}).get("tools") or []
    assert any(t.get("name") == "iris.wiki.list_notes" for t in tools)
    assert not any(t.get("call_path") == "mcp_bridge" for t in tools)
    print("agent_tool_registry self-check ok", len(tools), "tools")
