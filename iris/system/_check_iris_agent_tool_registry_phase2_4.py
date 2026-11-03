"""Phase 2.4 Iris Agent native wiki.search + MCP product-path shrink 자검.

- iris.wiki.search 가 native 로 등록되고 speak 경로에서 동작한다.
- speak / invoke_native_tool / try_native_control_invoke 가 list·search 에
  MCP stdio·Control HTTP 를 쓰면 실패한다.
- iris_control_stdio iris_invoke 가 wiki.list_notes / wiki.search 를
  native 로 리다이렉트한다 (이름만 바꾼 MCP = plan B 금지).
- 비-seed Control 액션은 여전히 HTTP compat 가능 (147 전체 MCP 삭제 주장 금지).
"""

from __future__ import annotations

import json
import socket
from unittest import mock

from iris.infrastructure.agent_tool_registry import (
    default_registry,
    native_tool_for_control_action,
    resolve_speak_tool_name,
    speak_invoke_agent_tool,
    try_native_control_invoke,
)
from iris.mcp import iris_control_stdio
from iris.system.hermes_iris_control_sync import project_root
from iris.ui.workers.hermes_workers import HermesChatWorker


def _block_network(*_a: object, **_k: object) -> None:
    raise AssertionError(
        "Phase 2.4 native wiki list/search must not open network or MCP Control HTTP"
    )


def _main() -> None:
    root = project_root()
    reg = default_registry()
    by_name = {t["name"]: t for t in reg.catalog()}

    assert by_name["iris.wiki.list_notes"]["call_path"] == "native"
    assert by_name["iris.wiki.search"]["call_path"] == "native"
    assert "iris.wiki.search" in reg.native_names()
    assert resolve_speak_tool_name("wiki.search") == "iris.wiki.search"
    assert native_tool_for_control_action("wiki.list_notes") == "iris.wiki.list_notes"
    assert native_tool_for_control_action("wiki.search") == "iris.wiki.search"
    # Phase 2.5+ : seed mail is native (gate 1). Uncovered non-seed stays None.
    assert native_tool_for_control_action("email.list_accounts") == (
        "iris.mail.list_accounts"
    )
    assert native_tool_for_control_action("email.list_messages") is None

    with mock.patch("socket.socket", side_effect=_block_network):
        with mock.patch("socket.create_connection", side_effect=_block_network):
            listed = HermesChatWorker.invoke_native_tool(
                "iris.wiki.list_notes",
                {"limit": 2},
            )
            searched = speak_invoke_agent_tool(
                "wiki.search",
                {"query": "iris", "limit": 2},
                registry=reg,
            )
            via_mcp_list = try_native_control_invoke(
                "wiki.list_notes",
                {"limit": 1},
                registry=reg,
            )
            via_mcp_search = try_native_control_invoke(
                "wiki.search",
                {"query": "iris", "limit": 1},
                registry=reg,
            )
    assert listed.get("ok") is True, listed
    assert listed.get("call_path") == "native"
    assert (listed.get("data") or {}).get("bridge") == "none"
    assert searched.get("ok") is True, searched
    assert searched.get("call_path") == "native"
    assert (searched.get("data") or {}).get("bridge") == "none"
    assert "hits" in (searched.get("data") or {})
    assert via_mcp_list is not None and via_mcp_list.get("ok") is True
    assert via_mcp_list.get("call_path") == "native"
    assert via_mcp_list.get("bridge") == "none"
    assert via_mcp_search is not None and via_mcp_search.get("ok") is True
    assert via_mcp_search.get("call_path") == "native"

    # MCP stdio iris_invoke for covered wiki actions must not call Control HTTP.
    with mock.patch.object(
        iris_control_stdio,
        "_http",
        side_effect=AssertionError(
            "Phase 2.4 MCP iris_invoke wiki must not hit Control HTTP"
        ),
    ):
        with mock.patch("socket.socket", side_effect=_block_network):
            mcp_list = iris_control_stdio._handle_tool(
                "iris_invoke",
                {"action": "wiki.list_notes", "args": {"limit": 1}},
            )
            mcp_search = iris_control_stdio._handle_tool(
                "iris_invoke",
                {"action": "wiki.search", "args": {"query": "iris", "limit": 1}},
            )
    assert mcp_list.get("isError") is False
    list_payload = json.loads(mcp_list["content"][0]["text"])
    assert list_payload.get("ok") is True
    assert list_payload.get("call_path") == "native"
    assert list_payload.get("bridge") == "none"
    search_payload = json.loads(mcp_search["content"][0]["text"])
    assert search_payload.get("ok") is True
    assert search_payload.get("call_path") == "native"

    # Non-seed action still would use HTTP (prove we did not rename-only MCP).
    still_http = try_native_control_invoke("email.list_messages", {}, registry=reg)
    assert still_http is None

    workers_src = (
        root / "iris" / "ui" / "workers" / "hermes_workers.py"
    ).read_text(encoding="utf-8")
    assert "iris.wiki.search" in workers_src
    assert "self._wire_native_speak_tools()" in workers_src

    reg_src = (
        root / "iris" / "infrastructure" / "agent_tool_registry.py"
    ).read_text(encoding="utf-8")
    assert "def try_native_control_invoke" in reg_src
    assert "_handle_wiki_search" in reg_src
    assert "8765" not in reg_src
    assert "iris_control_stdio" not in reg_src

    stdio_src = (root / "iris" / "mcp" / "iris_control_stdio.py").read_text(
        encoding="utf-8"
    )
    assert "try_native_control_invoke" in stdio_src
    # plan B ban: must still be able to HTTP for non-native; not rename-only server
    assert '_http("POST", "/v1/invoke"' in stdio_src
    assert "iris-tools" not in stdio_src

    skill = (
        root
        / "integrations"
        / "hermes-skills"
        / "iris-control"
        / "iris-wiki"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "hermes" not in skill.lower()
    assert "mcp__iris_control__" not in skill
    assert "iris.wiki.search" in skill
    assert "iris.wiki.list_notes" in skill

    nudge_src = (root / "iris" / "system" / "hermes_memory_nudge.py").read_text(
        encoding="utf-8"
    )
    assert "iris.wiki.search" in nudge_src
    assert "iris.wiki.list_notes" in nudge_src
    assert "iris-control-nudge-v2" in nudge_src

    assert isinstance(socket.socket, type)
    print(
        "iris_agent_tool_registry_phase2_4 ok",
        f"wiki_search hits={(searched.get('data') or {}).get('count')}",
        f"native={reg.native_names()}",
    )


if __name__ == "__main__":
    _main()
