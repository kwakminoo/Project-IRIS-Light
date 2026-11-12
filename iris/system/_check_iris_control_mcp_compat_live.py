"""COMPAT env must not re-register iris-control MCP (complete removal)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from iris.system.iris_agent_control_sync import sync_iris_control


def _main() -> None:
    with TemporaryDirectory() as tmp:
        home = Path(tmp) / "hermes"
        with (
            patch.dict("os.environ", {"IRIS_CONTROL_MCP_COMPAT": "1"}),
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
            report = sync_iris_control(home=home, reconnect_gateway=False)
            summary = report.summary_line()
            assert report.mcp_installed, summary
            assert "SpeakTools" in summary, summary
            assert "MCP iris-control ok" not in summary, summary
            data = yaml.safe_load(
                (home / "config.yaml").read_text(encoding="utf-8")
            ) or {}
            servers = data.get("mcp_servers") or {}
            assert "iris-control" not in servers, servers
            assert "mobile-mcp" in servers, servers
            assert all(
                "iris-control MCP still listed" not in e for e in report.errors
            ), report.errors
            print("iris_control_mcp_compat_live ok", summary)


if __name__ == "__main__":
    _main()
