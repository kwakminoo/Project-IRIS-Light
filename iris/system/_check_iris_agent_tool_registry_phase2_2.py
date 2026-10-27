"""Phase 2.2 Iris Agent tool registry 자검.

- iris.wiki.list_notes 는 native 핸들러로 등록된다.
- invoke_agent_tool 경로로 호출되며 MCP stdio·:8765 가 필요하면 실패한다.
- iris-wiki 스킬 사용자 문구에 hermes / mcp__iris_control__ 가 없다.
- plan B (MCP 이름만 변경) 로 완료 처리하지 않았음을 소스에서 확인한다.
"""

from __future__ import annotations

import socket
from unittest import mock

from iris.infrastructure.agent_tool_registry import (
    default_registry,
    invoke_agent_tool,
)
from iris.system.hermes_iris_control_sync import project_root


def _block_network(*_a: object, **_k: object) -> None:
    raise AssertionError(
        "Phase 2.2 iris.wiki.list_notes must not open network or MCP Control"
    )


def _main() -> None:
    root = project_root()
    reg = default_registry()
    catalog = reg.catalog()
    by_name = {t["name"]: t for t in catalog}
    assert "iris.wiki.list_notes" in by_name
    assert by_name["iris.wiki.list_notes"]["call_path"] == "native"
    assert "iris.wiki.list_notes" in reg.native_names()

    # Documented speak/agent invoke path: no TCP, no MCP, no Control URL.
    with mock.patch("socket.socket", side_effect=_block_network):
        with mock.patch("socket.create_connection", side_effect=_block_network):
            listed = invoke_agent_tool(
                "iris.wiki.list_notes",
                {"limit": 5},
                registry=reg,
            )
    assert listed.get("ok") is True, listed
    assert listed.get("call_path") == "native"
    data = listed.get("data") or {}
    assert data.get("bridge") == "none"
    assert "notes" in data
    assert "total" in data
    assert isinstance(data["notes"], list)
    assert data["count"] == len(data["notes"])
    assert data["count"] <= 5

    # Phase 2.5+: seed mail is native (gate 1 closed).
    mail = invoke_agent_tool("iris.mail.list_accounts", {}, registry=reg)
    assert mail.get("ok") is True, mail
    assert mail.get("call_path") == "native"
    assert (mail.get("data") or {}).get("bridge") == "none"

    reg_src = (root / "iris" / "infrastructure" / "agent_tool_registry.py").read_text(
        encoding="utf-8"
    )
    assert "iris_control_stdio" not in reg_src
    assert "8765" not in reg_src
    assert "def invoke_agent_tool" in reg_src
    assert 'name="iris.wiki.list_notes"' in reg_src
    assert 'call_path="native"' in reg_src
    assert "mcp_servers" not in reg_src
    assert "_handle_wiki_list_notes" in reg_src

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
    assert "Prefer Iris Control MCP" not in skill
    assert "iris.wiki.list_notes" in skill or "wiki.list_notes" in skill

    assert isinstance(socket.socket, type)

    print(
        "iris_agent_tool_registry_phase2_2 ok",
        f"wiki_list total={data.get('total')}",
        f"native={reg.native_names()}",
    )


if __name__ == "__main__":
    _main()
