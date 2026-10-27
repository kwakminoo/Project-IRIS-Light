"""Phase 2.1 Iris Agent tool registry 자검.

- 제품 측 native registry 가 존재하고 catalog 를 소유한다.
- iris.tools.ping / iris.tools.catalog 는 MCP stdio·:8765 없이 호출된다.
- SOUL 에 Hermes 부정문이 없다.
- 손댄 iris-control 스킬 사용자 문구에 Hermes 가 없다.
- plan B (MCP 이름만 변경) 로 완료 처리하지 않았음을 소스에서 확인한다.
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest import mock

from iris.infrastructure.agent_tool_registry import default_registry
from iris.system.hermes_iris_control_sync import project_root


def _block_network(*_a: object, **_k: object) -> None:
    raise AssertionError("Phase 2.1 native invoke must not open network")


def _main() -> None:
    root = project_root()
    reg = default_registry()
    catalog = reg.catalog()
    assert len(catalog) >= 2
    native = {t["name"] for t in catalog if t["call_path"] == "native"}
    assert "iris.tools.ping" in native
    assert "iris.tools.catalog" in native
    # Phase 2.2 adds domain native; 2.1 regression still requires ping/catalog.
    domains = {t["domain"] for t in catalog}
    for need in ("session", "wiki", "mail", "ide", "project"):
        assert need in domains, need

    # Prove native path: no TCP, no MCP module, no Control URL.
    with mock.patch("socket.socket", side_effect=_block_network):
        with mock.patch("socket.create_connection", side_effect=_block_network):
            ping = reg.invoke("iris.tools.ping")
            cat = reg.invoke("iris.tools.catalog")
    assert ping.get("ok") is True
    assert ping.get("call_path") == "native"
    assert (ping.get("data") or {}).get("bridge") == "none"
    assert cat.get("ok") is True
    tools = (cat.get("data") or {}).get("tools") or []
    assert len(tools) == len(catalog)

    # Phase 2.5+: seed mail is native. Catalog must not advertise mcp_bridge.
    mail = reg.invoke("iris.mail.list_accounts", {})
    assert mail.get("ok") is True, mail
    assert mail.get("call_path") == "native"
    assert not any(t.get("call_path") == "mcp_bridge" for t in catalog)

    # Registry module must not import MCP stdio or hard-code :8765 product path
    reg_src = (root / "iris" / "infrastructure" / "agent_tool_registry.py").read_text(
        encoding="utf-8"
    )
    assert "iris_control_stdio" not in reg_src
    assert "8765" not in reg_src
    # plan B = rename MCP only; native call_path must exist and dominate dry-run
    assert 'call_path="native"' in reg_src or "call_path: CallPath" in reg_src
    assert "mcp_servers" not in reg_src


    soul = (root / "integrations" / "hermes-soul" / "SOUL.md").read_text(
        encoding="utf-8"
    )
    assert "아이리스" in soul or "IRIS" in soul
    assert "Hermes가 아니다" not in soul
    assert "Hermes Agent가 아니다" not in soul

    skill_dirs = [
        root / "integrations" / "hermes-skills" / "iris-control" / "iris-session-status",
        root / "integrations" / "hermes-skills" / "iris-control" / "iris-work-start",
    ]
    for skill_dir in skill_dirs:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "hermes" not in text.lower(), skill_dir.name
        assert "mcp__iris_control__" not in text, skill_dir.name

    # socket still works for unrelated code (sanity)
    assert isinstance(socket.socket, type)

    print(
        "iris_agent_tool_registry_phase2 ok",
        f"tools={len(catalog)}",
        f"native={sorted(native)}",
    )


if __name__ == "__main__":
    _main()
