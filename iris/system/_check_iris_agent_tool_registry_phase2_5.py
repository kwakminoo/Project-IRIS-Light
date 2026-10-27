"""Phase 2.5 / §10.1 gate 1 — product seed path all-native 자검.

CLOSED bar (honest):
- _SEED 에 mcp_bridge 행 0
- 모든 seed 에 native handler
- speak / try_native_control_invoke 가 seed control_action 을 :8765 없이 호출
- 비-seed iris_invoke 는 HTTP compat 가능 (plan B rename-only 금지)
- 147 MCP 전체 삭제 주장 금지
"""

from __future__ import annotations

import json
import socket
from unittest import mock

from iris.infrastructure.agent_tool_registry import (
    _SEED,
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
        "Phase 2.5 seed native path must not open network or Control HTTP"
    )


_SEED_ACTIONS = (
    "wiki.list_notes",
    "wiki.search",
    "email.list_accounts",
    "calendar.list_events",
    "get_state",
    "ide.open_folder",
    "project.open_similar",
    "ping",
    "get_catalog",
)


def _main() -> None:
    root = project_root()
    reg = default_registry()
    catalog = reg.catalog()

    assert all(t.call_path == "native" for t in _SEED), [
        (t.name, t.call_path) for t in _SEED if t.call_path != "native"
    ]
    assert not any(row.get("call_path") == "mcp_bridge" for row in catalog)
    for row in catalog:
        assert row["call_path"] == "native"
        assert row["name"] in reg.native_names()

    assert resolve_speak_tool_name("email.list_accounts") == "iris.mail.list_accounts"
    assert resolve_speak_tool_name("calendar.list_events") == (
        "iris.calendar.list_events"
    )
    assert resolve_speak_tool_name("get_state") == "iris.session.get_state"
    assert native_tool_for_control_action("email.list_accounts") == (
        "iris.mail.list_accounts"
    )
    assert native_tool_for_control_action("calendar.list_events") == (
        "iris.calendar.list_events"
    )
    assert native_tool_for_control_action("get_state") == "iris.session.get_state"
    assert native_tool_for_control_action("ide.open_folder") == "iris.ide.open_folder"
    assert native_tool_for_control_action("project.open_similar") == (
        "iris.project.open_similar"
    )

    with mock.patch("socket.socket", side_effect=_block_network):
        with mock.patch("socket.create_connection", side_effect=_block_network):
            mail = HermesChatWorker.invoke_native_tool("iris.mail.list_accounts", {})
            cal = speak_invoke_agent_tool(
                "calendar.list_events", {"limit": 2}, registry=reg
            )
            via_mail = try_native_control_invoke(
                "email.list_accounts", {}, registry=reg
            )
            via_cal = try_native_control_invoke(
                "calendar.list_events", {"limit": 1}, registry=reg
            )
            via_state = try_native_control_invoke("get_state", {}, registry=reg)
            via_ide = try_native_control_invoke(
                "ide.open_folder",
                {"path": "C:\\\\"},
                registry=reg,
            )
            via_proj = try_native_control_invoke(
                "project.open_similar",
                {"query": "iris light"},
                registry=reg,
            )

    assert mail.get("ok") is True, mail
    assert mail.get("call_path") == "native"
    assert (mail.get("data") or {}).get("bridge") == "none"
    assert "accounts" in (mail.get("data") or {})
    assert cal.get("ok") is True, cal
    assert cal.get("call_path") == "native"
    assert "events" in (cal.get("data") or {})
    assert via_mail is not None and via_mail.get("call_path") == "native"
    assert via_mail.get("bridge") == "none"
    assert via_cal is not None and via_cal.get("call_path") == "native"
    assert via_state is not None and via_state.get("call_path") == "native"
    assert via_state.get("bridge") == "none"
    # Headless / no MainWindow → structured requires_iris_ui, still native (no :8765).
    assert via_state.get("ok") is False
    assert via_state.get("error") == "requires_iris_ui"
    assert via_ide is not None and via_ide.get("call_path") == "native"
    assert via_ide.get("ok") is False
    assert via_ide.get("error") == "requires_iris_ui"
    assert via_proj is not None and via_proj.get("ok") is False
    assert via_proj.get("error") == "requires_iris_ui"

    with mock.patch.object(
        iris_control_stdio,
        "_http",
        side_effect=AssertionError(
            "Phase 2.5 MCP iris_invoke seed tools must not hit Control HTTP"
        ),
    ):
        with mock.patch("socket.socket", side_effect=_block_network):
            for action, args in (
                ("email.list_accounts", {}),
                ("calendar.list_events", {"limit": 1}),
                ("get_state", {}),
                ("ide.open_folder", {"path": "C:\\\\"}),
                ("project.open_similar", {"query": "x"}),
                ("wiki.list_notes", {"limit": 1}),
                ("wiki.search", {"query": "iris", "limit": 1}),
            ):
                mcp = iris_control_stdio._handle_tool(
                    "iris_invoke",
                    {"action": action, "args": args},
                )
                assert mcp.get("isError") is False, (action, mcp)
                payload = json.loads(mcp["content"][0]["text"])
                assert payload.get("call_path") == "native", (action, payload)
                assert payload.get("bridge") == "none"

    # Non-seed still may HTTP — prove not plan B rename-only MCP.
    assert try_native_control_invoke("email.list_messages", {}, registry=reg) is None
    assert try_native_control_invoke("wiki.write_user_note", {}, registry=reg) is None

    workers_src = (
        root / "iris" / "ui" / "workers" / "hermes_workers.py"
    ).read_text(encoding="utf-8")
    assert "iris.mail.list_accounts" in workers_src
    assert "iris.calendar.list_events" in workers_src
    assert "self._wire_native_speak_tools()" in workers_src
    wire_start = workers_src.index("def _wire_native_speak_tools")
    wire_end = workers_src.index("def run(self)", wire_start)
    wire_body = workers_src[wire_start:wire_end]
    assert "iris.ide.open_folder" not in wire_body
    assert "iris.project.open_similar" not in wire_body
    assert "8765" not in wire_body

    reg_src = (
        root / "iris" / "infrastructure" / "agent_tool_registry.py"
    ).read_text(encoding="utf-8")
    assert "_handle_mail_list_accounts" in reg_src
    assert "_handle_calendar_list_events" in reg_src
    assert "requires_iris_ui" in reg_src
    assert "8765" not in reg_src
    assert "iris_control_stdio" not in reg_src
    assert 'call_path="mcp_bridge"' not in reg_src

    stdio_src = (root / "iris" / "mcp" / "iris_control_stdio.py").read_text(
        encoding="utf-8"
    )
    assert "try_native_control_invoke" in stdio_src
    assert '_http("POST", "/v1/invoke"' in stdio_src

    for skill_name, markers in (
        ("iris-email", ("iris.mail.list_accounts",)),
        ("iris-calendar", ("iris.calendar.list_events",)),
        ("iris-session-status", ("iris.session.get_state",)),
        ("iris-work-start", ("iris.ide.open_folder", "iris.project.open_similar")),
    ):
        skill = (
            root
            / "integrations"
            / "hermes-skills"
            / "iris-control"
            / skill_name
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "mcp__iris_control__" not in skill, skill_name
        for marker in markers:
            assert marker in skill, (skill_name, marker)

    nudge_src = (root / "iris" / "system" / "hermes_memory_nudge.py").read_text(
        encoding="utf-8"
    )
    assert "iris.mail.list_accounts" in nudge_src
    assert "iris.calendar.list_events" in nudge_src
    assert "iris.session.get_state" in nudge_src
    assert "iris-control-nudge-v" in nudge_src
    assert "project.create_scaffold" in nudge_src

    # archive-finished-reports: closed Phase 2.5 / path docs live under completed/.
    completed = root / "docs" / "code-review" / "completed"
    report = (completed / "Iris-Agent-tool-registry-Phase2.5.md").read_text(
        encoding="utf-8"
    )
    assert "CLOSED" in report
    assert "구조" in report
    assert "코드 리뷰" in report
    assert "차용" in report

    path_doc = (completed / "Iris-Agent-Hermes기반-구현경로.md").read_text(
        encoding="utf-8"
    )
    assert "1 **CLOSED**" in path_doc
    assert "→ **CLOSED** (Phase 2.5" in path_doc
    assert "일체화 완료" in path_doc

    assert isinstance(socket.socket, type)
    print(
        "iris_agent_tool_registry_phase2_5 ok",
        f"seed={len(_SEED)}",
        f"actions_covered={len(_SEED_ACTIONS)}",
        f"native={reg.native_names()}",
    )


if __name__ == "__main__":
    _main()
