"""Unit A — product sync never registers iris-control MCP (no COMPAT escape).

Speak path is SpeakTools only. sync always scrubs mcp_servers.iris-control.
MEMORY nudge must not teach mcp__iris_control__* or IRIS_CONTROL_MCP_COMPAT.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from iris.browser.observation import browser_teaching_block
from iris.infrastructure import agent_runtime as ar
from iris.mcp import iris_control_stdio as stdio
from iris.system import iris_agent_memory_nudge as nudge
from iris.system.iris_agent_control_sync import (
    ensure_mcp_in_config,
    project_root,
    sync_iris_control,
    verify_install,
)
from iris.system.iris_agent_gateway import verify_iris_mcp_tools


_ROOT = Path(__file__).resolve().parents[2]
_MCP_TEACH = re.compile(r"mcp__iris_control__|IRIS_CONTROL_MCP_COMPAT", re.I)


def _assert_memory_nudge_speak_tools_product() -> None:
    assert nudge._MARKER in nudge._BLOCK, "nudge version marker drift"
    block = nudge._nudge_block()
    assert "Prefer product **SpeakTools**" in block
    assert "IRIS_CONTROL_MCP_COMPAT" not in block
    assert "mcp__iris_control__" not in block
    for line in block.splitlines():
        head = line.strip()
        if not head:
            continue
        if _MCP_TEACH.search(head):
            raise AssertionError(
                "MEMORY must not teach iris-control MCP or COMPAT: " + head[:160]
            )
    item19 = block.split("\n19.", 1)[-1].split("\n20.", 1)[0]
    assert "SpeakTools" in item19 or "control" in item19.lower(), item19
    assert "IRIS_CONTROL_MCP_COMPAT" not in item19, item19
    assert "mcp__iris_control__" not in item19, item19
    assert "Iris Control MCP is offline" not in item19, item19
    teach = browser_teaching_block()
    assert "iris_invoke" not in teach, teach[:200]
    assert "SpeakTools" in teach or "control" in teach.lower()

    writers = [
        n
        for n in ast.walk(
            ast.parse(
                (_ROOT / "iris" / "system" / "iris_agent_memory_nudge.py").read_text(
                    encoding="utf-8"
                )
            )
        )
        if isinstance(n, ast.FunctionDef) and n.name == "ensure_memory_nudge"
    ]
    assert len(writers) == 1
    assert "MEMORY.md" not in ar._MIGRATE_FILES
    assert "USER.md" not in ar._MIGRATE_FILES
    assert "memories" in ar._MIGRATE_DIRS

    with TemporaryDirectory() as tmp:
        home = Path(tmp) / "agent-home"
        home.mkdir()
        dual = home / "MEMORY.md"
        dual.write_text(
            "<!-- iris-control-nudge-v1 -->\nold mcp seed\nmcp__iris_control__iris_invoke\n",
            encoding="utf-8",
        )
        msg = nudge.ensure_memory_nudge(home=home)
        assert "updated" in msg or "present" in msg, msg
        product = home / "memories" / "MEMORY.md"
        assert product.is_file()
        text = product.read_text(encoding="utf-8")
        assert nudge._MARKER in text
        assert "Prefer product **SpeakTools**" in text
        assert "IRIS_CONTROL_MCP_COMPAT" not in text
        assert "mcp__iris_control__" not in text
        dual_text = dual.read_text(encoding="utf-8")
        assert "iris-control-nudge" not in dual_text, dual_text


def _assert_scrub_even_with_compat_env() -> None:
    with TemporaryDirectory() as tmp:
        home = Path(tmp) / "hermes-home"
        home.mkdir()
        (home / "config.yaml").write_text(
            "mcp_servers:\n  iris-control:\n    command: stale\n    args: []\n",
            encoding="utf-8",
        )
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
            installed, _changed, msg = ensure_mcp_in_config(
                project_root(), home=home
            )
            assert installed, msg
            servers = (
                yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
                or {}
            ).get("mcp_servers") or {}
            assert "iris-control" not in servers, servers
            assert "mobile-mcp" in servers, servers
            report = sync_iris_control(home=home, reconnect_gateway=False)
            assert report.mcp_installed
            assert "SpeakTools" in report.summary_line()
            assert "MCP iris-control ok" not in report.summary_line()
            assert "iris-control" not in (
                (yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {})
                .get("mcp_servers")
                or {}
            )
            assert all(
                "iris-control MCP still listed" not in e for e in report.errors
            ), report.errors


def _main() -> None:
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
            installed, _changed, msg = ensure_mcp_in_config(
                project_root(), home=home
            )
            assert installed, msg
            data = yaml.safe_load(
                (home / "config.yaml").read_text(encoding="utf-8")
            ) or {}
            servers = data.get("mcp_servers") or {}
            assert "iris-control" not in servers, servers
            assert "mobile-mcp" in servers, servers

            report = sync_iris_control(home=home, reconnect_gateway=False)
            assert report.mcp_installed
            assert "SpeakTools" in report.summary_line()
            assert "MCP iris-control ok" not in report.summary_line()
            assert "iris-control" not in (
                yaml.safe_load(
                    (home / "config.yaml").read_text(encoding="utf-8")
                ) or {}
            ).get("mcp_servers", {})
            # Unit A: MCP scrub only; skill-catalog drift is out of scope.
            assert all(
                "iris-control MCP still listed" not in e for e in report.errors
            ), report.errors
            verified = verify_install(home=home)
            assert verified.mcp_installed
            assert all(
                "mcp iris-control not present" not in e for e in verified.errors
            )
            assert all("must be absent" not in e for e in verified.errors)
            assert all(
                "iris-control MCP still listed" not in e for e in verified.errors
            ), verified.errors
            nudge_msgs = [m for m in report.messages if "memory nudge" in m]
            assert nudge_msgs, report.messages
            assert all("skip:" not in m for m in nudge_msgs), nudge_msgs
            assert (home / "memories" / "MEMORY.md").is_file()

    _assert_scrub_even_with_compat_env()

    mcp_ok, mcp_detail = verify_iris_mcp_tools()
    assert mcp_ok, mcp_detail
    assert "SpeakTools" in mcp_detail or "not product-required" in mcp_detail

    sync_src = (
        _ROOT / "iris" / "system" / "iris_agent_control_sync.py"
    ).read_text(encoding="utf-8")
    assert "iris_control_mcp_compat_enabled" not in sync_src
    assert "IRIS_CONTROL_MCP_COMPAT" not in sync_src
    assert "SpeakTools" in sync_src or "speak" in sync_src.lower()
    assert sync_src.count("ensure_memory_nudge(") == 1

    stdio_src = (_ROOT / "iris" / "mcp" / "iris_control_stdio.py").read_text(
        encoding="utf-8"
    )
    assert "IRIS_CONTROL_MCP_COMPAT" not in stdio_src
    assert "iris_control_mcp_compat_enabled" not in stdio_src
    assert "SpeakTools" in stdio_src
    with patch.dict("os.environ", {"IRIS_CONTROL_MCP_COMPAT": "1"}):
        assert stdio.main() != 0

    _assert_memory_nudge_speak_tools_product()

    print("product_no_iris_control_mcp ok", msg[:80])


if __name__ == "__main__":
    _main()
