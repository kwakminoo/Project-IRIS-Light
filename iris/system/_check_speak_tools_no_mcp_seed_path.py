"""Step3 — SpeakTools seed/wiki path works with iris-control MCP absent."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.system.iris_agent_control_sync import (
    ensure_mcp_in_config,
    project_root,
    sync_iris_control,
)


def _main() -> None:
    listed = speak_invoke_agent_tool("wiki.list_notes", {"limit": 1})
    assert listed.get("ok") is True, listed
    assert listed.get("call_path") == "native", listed
    assert listed.get("bridge") == "none", listed

    write = speak_invoke_agent_tool(
        "wiki.write_user_note", {"title": "t", "content": "c"}
    )
    assert write.get("call_path") == "native", write
    assert write.get("ok") is False, write
    assert write.get("error") == "requires_iris_ui", write

    with TemporaryDirectory() as tmp:
        home = Path(tmp) / "hermes-home"
        home.mkdir()
        (home / "config.yaml").write_text(
            "mcp_servers:\n  iris-control:\n    command: stale\n    args: []\n",
            encoding="utf-8",
        )
        with (
            patch(
                "iris.system.iris_agent_control_sync.hermes_home",
                return_value=home,
            ),
            patch(
                "iris.system.iris_agent_soul_sync.hermes_home",
                return_value=home,
            ),
            patch(
                "iris.system.iris_agent_memory_nudge.hermes_home",
                return_value=home,
            ),
        ):
            ok, _changed, msg = ensure_mcp_in_config(project_root(), home=home)
            assert ok, msg
            servers = (
                yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
            ).get("mcp_servers") or {}
            assert "iris-control" not in servers, servers
            report = sync_iris_control(home=home, reconnect_gateway=False)
            assert report.ok, report.errors
            assert "SpeakTools" in report.summary_line()
            assert "iris-control" not in (
                (yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {})
                .get("mcp_servers")
                or {}
            )

    print(
        "speak_tools_no_mcp_seed_path ok",
        f"wiki_total={(listed.get('data') or {}).get('total')}",
    )


if __name__ == "__main__":
    _main()
