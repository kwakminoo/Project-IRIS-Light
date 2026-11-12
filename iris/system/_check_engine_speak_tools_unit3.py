"""Unit3 — engine/speak bind: IRIS_ENGINE_TOOLS is SpeakTools, not MCP triple.

Fails while types.IRIS_ENGINE_TOOLS is still
(iris_get_state, iris_get_catalog, iris_invoke). Green when product engine
list is SpeakTools.engine_names() and boot assert rejects the MCP triple.
MCP stdio install path stays for Unit4.
"""

from __future__ import annotations

from pathlib import Path

from iris.engine.types import IRIS_ENGINE_TOOLS, assert_iris_engine_tools_catalog
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    assert_engine_tools_match_allowlist,
    default_speak_tools,
)
from iris.mcp.iris_control_stdio import TOOLS
from iris.ui.workers.iris_agent_workers import HermesChatWorker


_MCP_TRIPLE = ("iris_get_state", "iris_get_catalog", "iris_invoke")
_ROOT = Path(__file__).resolve().parents[2]


def _main() -> None:
    assert IRIS_ENGINE_TOOLS != _MCP_TRIPLE, (
        "IRIS_ENGINE_TOOLS must not remain the MCP iris-control triple"
    )
    assert IRIS_ENGINE_TOOLS == PHASE4_ALLOWLIST.names()
    assert IRIS_ENGINE_TOOLS == default_speak_tools().engine_names()
    assert "chat.set_title" in IRIS_ENGINE_TOOLS
    assert "project.run" in IRIS_ENGINE_TOOLS
    assert "iris_invoke" not in IRIS_ENGINE_TOOLS

    assert_iris_engine_tools_catalog()
    assert_engine_tools_match_allowlist(IRIS_ENGINE_TOOLS)

    try:
        assert_iris_engine_tools_catalog(_MCP_TRIPLE)
        raise AssertionError("boot assert must reject MCP triple")
    except AssertionError as exc:
        msg = str(exc)
        assert "MCP triple" in msg or "iris_get_state" in msg or "allowlist" in msg

    try:
        assert_engine_tools_match_allowlist(_MCP_TRIPLE)
        raise AssertionError("allowlist assert must reject MCP triple")
    except AssertionError as exc:
        assert "MCP triple" in str(exc) or "iris_get_state" in str(exc)

    assert HermesChatWorker.engine_tool_names() == IRIS_ENGINE_TOOLS
    listed = HermesChatWorker.invoke_native_tool("wiki.list_notes", {"limit": 1})
    assert listed.get("call_path") == "native", listed
    assert listed.get("ok") is True, listed
    titled = HermesChatWorker.invoke_native_tool("chat.set_title", {"title": "u3"})
    assert titled.get("call_path") == "native", titled

    workers_text = (
        _ROOT / "iris" / "ui" / "workers" / "iris_agent_workers.py"
    ).read_text(encoding="utf-8")
    assert "def engine_tool_names" in workers_text
    assert "engine_names" in workers_text
    assert "self._wire_native_speak_tools()" in workers_text
    wire_start = workers_text.index("def _wire_native_speak_tools")
    wire_end = workers_text.index("def run(self)", wire_start)
    wire_body = workers_text[wire_start:wire_end]
    assert "engine_tool_names" in wire_body
    assert "wiki.list_notes" in wire_body
    assert "mcp__iris_control__" not in wire_body

    nudge = (_ROOT / "iris" / "system" / "iris_agent_memory_nudge.py").read_text(
        encoding="utf-8"
    )
    for bare in (
        "chat.set_title",
        "settings.get",
        "wiki.write_user_note",
        "project.run",
        "get_state",
        "get_catalog",
        "chat.new_session",
    ):
        assert bare in nudge, bare
    item5 = nudge.split("\n5.", 1)[-1].split("\n6.", 1)[0]
    assert "mcp__iris_control__iris_invoke" not in item5, item5
    assert "project.run" in item5

    stdio_names = tuple(tool["name"] for tool in TOOLS)
    assert stdio_names == ()
    assert stdio_names != IRIS_ENGINE_TOOLS
    assert "shell.run" in IRIS_ENGINE_TOOLS

    print(
        "engine_speak_tools_unit3 ok",
        f"engine={len(IRIS_ENGINE_TOOLS)}",
        f"stdio={len(stdio_names)}",
    )


if __name__ == "__main__":
    _main()
