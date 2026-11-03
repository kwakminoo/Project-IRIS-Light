"""Phase 2.3 Iris Agent speak-path tool wire 자검.

- HermesChatWorker 가 speak_invoke_agent_tool / invoke_native_tool 로
  iris.wiki.list_notes 를 호출한다.
- 그 경로는 MCP stdio·Control HTTP 가 필요하면 실패한다.
- run() 이 _wire_native_speak_tools 를 호출한다 (죽은 메서드만 두지 않음).
- plan B(MCP 이름만 변경)로 완료 처리하지 않았음을 소스에서 확인한다.
"""

from __future__ import annotations

import socket
from unittest import mock

from iris.infrastructure.agent_tool_registry import (
    default_registry,
    resolve_speak_tool_name,
    speak_invoke_agent_tool,
)
from iris.system.hermes_iris_control_sync import project_root
from iris.ui.workers.hermes_workers import HermesChatWorker


def _block_network(*_a: object, **_k: object) -> None:
    raise AssertionError(
        "Phase 2.3 speak path iris.wiki.list_notes must not open network or MCP Control"
    )


def _main() -> None:
    root = project_root()
    assert resolve_speak_tool_name("wiki.list_notes") == "iris.wiki.list_notes"

    workers_src = (
        root / "iris" / "ui" / "workers" / "hermes_workers.py"
    ).read_text(encoding="utf-8")
    assert "speak_invoke_agent_tool" in workers_src
    assert "def invoke_native_tool" in workers_src
    assert "_wire_native_speak_tools" in workers_src
    assert "self._wire_native_speak_tools()" in workers_src
    assert "iris.wiki.list_notes" in workers_src
    assert "iris_control_stdio" not in workers_src
    assert "from iris.mcp" not in workers_src
    # Native speak wire body must not call Control HTTP helpers.
    wire_start = workers_src.index("def _wire_native_speak_tools")
    wire_end = workers_src.index("def run(self)", wire_start)
    wire_body = workers_src[wire_start:wire_end]
    assert "speak_invoke_agent_tool" in workers_src[
        workers_src.index("def invoke_native_tool") : wire_start
    ] or "speak_invoke_agent_tool" in wire_body or "invoke_native_tool" in wire_body
    assert "urlopen" not in wire_body
    assert "8765" not in wire_body
    assert "iris_control_stdio" not in wire_body

    reg_src = (
        root / "iris" / "infrastructure" / "agent_tool_registry.py"
    ).read_text(encoding="utf-8")
    assert "def speak_invoke_agent_tool" in reg_src
    assert "def invoke_agent_tool" in reg_src
    assert "8765" not in reg_src
    assert "iris_control_stdio" not in reg_src

    reg = default_registry()
    with mock.patch("socket.socket", side_effect=_block_network):
        with mock.patch("socket.create_connection", side_effect=_block_network):
            via_worker = HermesChatWorker.invoke_native_tool(
                "iris.wiki.list_notes",
                {"limit": 3},
            )
            via_alias = speak_invoke_agent_tool(
                "wiki.list_notes",
                {"limit": 2},
                registry=reg,
            )
    assert via_worker.get("ok") is True, via_worker
    assert via_worker.get("call_path") == "native"
    assert (via_worker.get("data") or {}).get("bridge") == "none"
    assert "notes" in (via_worker.get("data") or {})
    assert via_alias.get("ok") is True, via_alias
    assert via_alias.get("call_path") == "native"

    # Phase 2.5+: seed mail is native (gate 1). Non-seed still may HTTP compat.
    mail = HermesChatWorker.invoke_native_tool("iris.mail.list_accounts", {})
    assert mail.get("ok") is True, mail
    assert mail.get("call_path") == "native"
    assert (mail.get("data") or {}).get("bridge") == "none"

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
    assert "speak_invoke_agent_tool" in skill or "invoke_native_tool" in skill
    assert "iris.wiki.list_notes" in skill

    assert isinstance(socket.socket, type)
    print(
        "iris_agent_tool_registry_phase2_3 ok",
        f"wiki_list total={(via_worker.get('data') or {}).get('total')}",
        f"native={reg.native_names()}",
    )


if __name__ == "__main__":
    _main()
