"""Unit2 — SpeakAllowlist / SpeakTools (PHASE4 grants) 자검.

Fails first without speak_capability; green when SpeakTools routes
Control action names natively (no MCP/HTTP on speak path).
"""

from __future__ import annotations

from iris.infrastructure.agent_tool_registry import (
    speak_invoke_agent_tool,
    try_native_control_invoke,
)
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    SpeakAllowlist,
    SpeakGrant,
    SpeakTools,
    ToolResult,
    assert_engine_tools_match_allowlist,
    default_speak_tools,
    resolve_legacy_name,
)
from iris.ui.workers.iris_agent_workers import HermesChatWorker


_REQUIRED = frozenset(
    {
        "ping",
        "get_catalog",
        "get_state",
        "settings.get",
        "wiki.list_notes",
        "wiki.search",
        "wiki.write_user_note",
        "email.list_accounts",
        "calendar.list_events",
        "ide.open_folder",
        "project.open_similar",
        "project.run",
        "chat.set_title",
        "chat.search_past",
        "chat.new_session",
        "diagram.render",
    }
)


class _FakeActions:
    def __init__(self) -> None:
        self._rows = {
            "project.run": type(
                "S",
                (),
                {
                    "name": "project.run",
                    "summary": "Run in IDE terminal",
                    "risk": "medium",
                    "confirm_required": True,
                },
            )(),
            "wiki.write_user_note": type(
                "S",
                (),
                {
                    "name": "wiki.write_user_note",
                    "summary": "Save wiki note",
                    "risk": "medium",
                    "confirm_required": False,
                },
            )(),
            "chat.set_title": type(
                "S",
                (),
                {
                    "name": "chat.set_title",
                    "summary": "Rename chat",
                    "risk": "low",
                    "confirm_required": False,
                },
            )(),
            "settings.get": type(
                "S",
                (),
                {
                    "name": "settings.get",
                    "summary": "Get settings",
                    "risk": "low",
                    "confirm_required": False,
                },
            )(),
            "ide.open_folder": type(
                "S",
                (),
                {
                    "name": "ide.open_folder",
                    "summary": "Open folder",
                    "risk": "low",
                    "confirm_required": False,
                },
            )(),
        }

    def spec(self, name: str):
        return self._rows.get(name)

    def catalog(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "summary": s.summary,
                "risk": s.risk,
                "confirm_required": s.confirm_required,
            }
            for s in self._rows.values()
        ]


class _RecordingSurface:
    def __init__(self, reply: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.reply = reply

    def invoke(self, action: str, args: dict) -> dict | None:
        self.calls.append((action, dict(args)))
        return self.reply


def _main() -> None:
    names = set(PHASE4_ALLOWLIST.names())
    missing = _REQUIRED - names
    assert not missing, f"PHASE4_ALLOWLIST missing: {sorted(missing)}"
    assert all(not n.startswith("iris.") for n in names), names

    assert resolve_legacy_name("iris.wiki.list_notes") == "wiki.list_notes"
    assert resolve_legacy_name("wiki.write_user_note") == "wiki.write_user_note"
    assert resolve_legacy_name("iris.tools.ping") == "ping"

    surface = _RecordingSurface(
        {"ok": True, "action": "chat.set_title", "result": {"title": "t"}}
    )
    tools = SpeakTools(
        PHASE4_ALLOWLIST,
        surface=surface,
        actions=_FakeActions(),
        pure_handlers={
            "ping": lambda _a: ToolResult(
                ok=True, action="ping", data={"alive": True, "bridge": "none"}
            ),
            "wiki.list_notes": lambda _a: ToolResult(
                ok=True,
                action="wiki.list_notes",
                data={"notes": [], "count": 0, "total": 0, "bridge": "none"},
            ),
        },
    )

    rows = {r.name: r for r in tools.catalog()}
    assert "wiki.write_user_note" in rows
    assert rows["wiki.write_user_note"].needs_ui is True
    assert rows["project.run"].confirm_required is True
    assert rows["project.run"].risk == "medium"
    assert rows["ping"].needs_ui is False

    assert tools.engine_names() == PHASE4_ALLOWLIST.names()
    try:
        assert_engine_tools_match_allowlist(
            ("iris_get_state", "iris_get_catalog", "iris_invoke")
        )
        raise AssertionError("MCP triple must be rejected")
    except AssertionError as exc:
        msg = str(exc)
        assert "MCP triple" in msg or "iris_get_state" in msg

    pure = tools.invoke("ping", {})
    assert pure.ok is True
    assert pure.call_path == "native"
    assert pure.bridge == "none"

    unknown = tools.invoke("email.list_messages", {})
    assert unknown.ok is False

    for action in (
        "wiki.write_user_note",
        "ide.open_folder",
        "project.run",
        "chat.set_title",
        "settings.get",
    ):
        surface.calls.clear()
        surface.reply = {
            "ok": True,
            "action": action,
            "result": {"bridged": False},
        }
        out = tools.invoke(action, {"x": 1})
        assert out.ok is True, (action, out)
        assert out.call_path == "native"
        assert surface.calls == [(action, {"x": 1})], surface.calls

    bare = SpeakTools(
        PHASE4_ALLOWLIST,
        surface=_RecordingSurface(None),
        actions=_FakeActions(),
        pure_handlers={},
    )
    ui = bare.invoke("wiki.write_user_note", {"title": "a", "content": "b"})
    assert ui.ok is False
    assert ui.error == "requires_iris_ui"
    assert ui.bridge == "none"
    assert ui.call_path == "native"

    write = speak_invoke_agent_tool(
        "wiki.write_user_note", {"title": "t", "content": "c"}
    )
    assert write.get("call_path") == "native", write
    assert write.get("ok") is False
    assert write.get("error") == "requires_iris_ui"
    assert write.get("bridge") == "none"

    titled = speak_invoke_agent_tool("chat.set_title", {"title": "Sprint"})
    assert titled.get("call_path") == "native", titled
    assert titled.get("ok") is False
    assert titled.get("error") == "requires_iris_ui"

    via_mcp_shape = try_native_control_invoke(
        "wiki.write_user_note", {"title": "t", "content": "c"}
    )
    assert via_mcp_shape is not None
    assert via_mcp_shape.get("call_path") == "native"
    assert via_mcp_shape.get("error") == "requires_iris_ui"

    via_title = try_native_control_invoke("chat.set_title", {"title": "x"})
    assert via_title is not None
    assert via_title.get("call_path") == "native"

    via_run = try_native_control_invoke("project.run", {"file": "main.py"})
    assert via_run is not None
    assert via_run.get("call_path") == "native"

    listed = speak_invoke_agent_tool("wiki.list_notes", {"limit": 1})
    assert listed.get("ok") is True, listed
    assert listed.get("call_path") == "native"

    legacy = HermesChatWorker.invoke_native_tool("iris.wiki.list_notes", {"limit": 1})
    assert legacy.get("ok") is True, legacy
    assert legacy.get("call_path") == "native"

    live = default_speak_tools()
    assert "chat.set_title" in live.engine_names()
    assert "project.run" in live.engine_names()

    confirm_surface = _RecordingSurface(
        {
            "ok": False,
            "action": "project.run",
            "error": "human confirm required",
            "result": {"confirm_required": True},
        }
    )
    confirm_tools = SpeakTools(
        SpeakAllowlist(grants=(SpeakGrant("project.run", ExecKind.SURFACE),)),
        surface=confirm_surface,
        actions=_FakeActions(),
    )
    denied = confirm_tools.invoke("project.run", {"file": "x.py", "confirm": True})
    assert confirm_surface.calls[0][0] == "project.run"
    assert denied.ok is False

    print(
        "speak_tools_phase4 ok",
        f"grants={len(PHASE4_ALLOWLIST.names())}",
        f"engine={len(live.engine_names())}",
    )


if __name__ == "__main__":
    _main()
