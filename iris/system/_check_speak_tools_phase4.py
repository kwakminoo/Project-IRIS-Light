"""Unit2 — ToolAllowlist / SpeakTools (PHASE4 grants) 자검.

Fails first without tool_capability; green when SpeakTools routes
Control action names natively (no MCP/HTTP on speak path).
"""

from __future__ import annotations

from iris.infrastructure.agent_tool_registry import (
    speak_invoke_agent_tool,
    try_native_control_invoke,
)
from iris.engine.model_tool_names import (
    catalog_uses_model_tool_names,
    names_hidden_from_model,
)
from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    ToolAllowlist,
    ToolGrant,
    SpeakTools,
    ToolResult,
    assert_engine_tools_match_allowlist,
    default_agent_tools,
    engine_tool_name,
    engine_tool_schemas,
    resolve_legacy_name,
)
from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker


_REQUIRED = frozenset(
    {
        "ping",
        "get_catalog",
        "get_state",
        "control.invoke",
        "settings.get",
        "wiki.list_notes",
        "wiki.search",
        "wiki.write_user_note",
        "email.list_accounts",
        "calendar.list_events",
        "ide.open_folder",
        "ide.open_file",
        "project.open_similar",
        "project.run",
        "project.write_file",
        "project.read_file",
        "project.list_files",
        "project.rename_file",
        "chat.set_title",
        "chat.search_past",
        "chat.new_session",
        "diagram.render",
    }
)

# Twin map (Hermes file/terminal disabled → Iris Speak Control action).
# Engine schemas expose dotted actions as provider-safe underscores.
_FILE_TERMINAL_TWINS = (
    ("write_file", "project.write_file"),
    ("read_file", "project.read_file"),
    ("", "project.list_files"),
    ("", "ide.open_file"),
    ("", "project.rename_file"),
    ("terminal", "project.run"),
)
_HERMES_FILE_BARE = frozenset({"write_file", "read_file", "search_files"})


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
            "project.write_file": type(
                "S",
                (),
                {
                    "name": "project.write_file",
                    "summary": "Write file under bound workspace",
                    "risk": "medium",
                    "confirm_required": True,
                },
            )(),
            "project.read_file": type(
                "S",
                (),
                {
                    "name": "project.read_file",
                    "summary": "Read UTF-8 file from bound workspace",
                    "risk": "low",
                    "confirm_required": False,
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
            "ide.open_file": type(
                "S",
                (),
                {
                    "name": "ide.open_file",
                    "summary": "Open file in IDE",
                    "risk": "medium",
                    "confirm_required": False,
                },
            )(),
            "project.list_files": type(
                "S",
                (),
                {
                    "name": "project.list_files",
                    "summary": "List workspace files",
                    "risk": "low",
                    "confirm_required": False,
                },
            )(),
            "project.rename_file": type(
                "S",
                (),
                {
                    "name": "project.rename_file",
                    "summary": "Rename file under workspace",
                    "risk": "medium",
                    "confirm_required": True,
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
    assert rows["ping"].needs_ui is False
    # Folded Speak twins leave the model catalog; grant + ActionSpec still define risk.
    run_grant = PHASE4_ALLOWLIST.grant("project.run")
    assert run_grant is not None
    run_spec = _FakeActions().spec("project.run")
    assert run_spec is not None
    assert run_spec.confirm_required is True
    assert run_spec.risk == "medium"
    write_grant = PHASE4_ALLOWLIST.grant("project.write_file")
    assert write_grant is not None
    write_spec = _FakeActions().spec("project.write_file")
    assert write_spec is not None
    assert write_spec.confirm_required is True
    assert write_spec.risk == "medium"
    read_grant = PHASE4_ALLOWLIST.grant("project.read_file")
    assert read_grant is not None
    assert read_grant.kind is ExecKind.SURFACE
    assert PHASE4_ALLOWLIST.grant("local.read_file") is not None
    assert PHASE4_ALLOWLIST.grant("local.search_files") is not None

    schema_names = {str(row["name"]) for row in engine_tool_schemas()}
    folded = catalog_uses_model_tool_names()
    hidden = names_hidden_from_model() if folded else {}
    for _agent, iris_action in _FILE_TERMINAL_TWINS:
        assert iris_action in names, f"twin missing grant: {iris_action}"
        eng = engine_tool_name(iris_action)
        if folded and eng in hidden:
            assert eng not in schema_names, f"folded twin still on model schema: {eng}"
        else:
            assert eng in schema_names, iris_action
    if folded:
        assert "project_write_file" not in schema_names
        assert "project_read_file" not in schema_names
        assert "control_invoke" not in schema_names
        assert "project_run" not in schema_names
        assert "local_read_file" not in schema_names
        assert "local_search_files" not in schema_names
    else:
        assert "project_write_file" in schema_names
        assert "project_read_file" in schema_names
        assert "project_run" in schema_names
    # Grants stay even when model schemas fold the overlap names.
    assert "project.run" in names
    assert "local.read_file" in names
    assert "local.search_files" in names
    # Models must use Iris Speak twins; Hermes bare file tools are not engine schemas.
    assert not (_HERMES_FILE_BARE & schema_names), (
        f"Hermes bare file tools must not appear in engine schemas: "
        f"{sorted(_HERMES_FILE_BARE & schema_names)}"
    )

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

    legacy = IrisAgentChatWorker.invoke_native_tool("iris.wiki.list_notes", {"limit": 1})
    assert legacy.get("ok") is True, legacy
    assert legacy.get("call_path") == "native"

    live = default_agent_tools()
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
        ToolAllowlist(grants=(ToolGrant("project.run", ExecKind.SURFACE),)),
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
