"""Runnable MCP multi-server, serialization, and reconnect contract."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import yaml

from iris.mcp.native_manager import NativeMCPManager


SERVER = r'''
import json
import pathlib
import sys
import time

marker, lock_name, count_name = sys.argv[1:]
lock = pathlib.Path(lock_name)
count = pathlib.Path(count_name)
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method")
    if "id" not in req:
        continue
    if method == "initialize":
        result = {"protocolVersion": req["params"]["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": marker, "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "same", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        count.write_text(str(int(count.read_text()) + 1) if count.exists() else "1")
        try:
            lock.open("x").close()
        except FileExistsError:
            lock.with_suffix(".overlap").touch()
        time.sleep(0.25)
        lock.unlink(missing_ok=True)
        result = {"content": [{"type": "text", "text": marker}],
                  "structuredContent": {"marker": marker}, "isError": False}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}), flush=True)
'''

FLAKY = r'''
import json
import pathlib
import sys

sentinel = pathlib.Path(sys.argv[1])
for line in sys.stdin:
    req = json.loads(line)
    if req.get("method") == "initialize" and not sentinel.exists():
        sentinel.touch()
        sys.exit(17)
    if "id" not in req:
        continue
    if req.get("method") == "initialize":
        result = {"protocolVersion": req["params"]["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": "flaky", "version": "1"}}
    elif req.get("method") == "tools/list":
        result = {"tools": []}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}), flush=True)
'''


def main() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        servers = {}
        paths = {}
        for name in ("alpha", "beta"):
            script = root / f"{name}.py"
            script.write_text(SERVER, encoding="utf-8")
            lock, count = root / f"{name}.lock", root / f"{name}.count"
            paths[name] = lock, count
            servers[name] = {
                "command": sys.executable,
                "args": [str(script), name, str(lock), str(count)],
                "model_enabled": True,
            }
        (root / "config.yaml").write_text(
            yaml.safe_dump({"mcp_servers": servers}), encoding="utf-8"
        )
        manager = NativeMCPManager(home=root)
        bindings = manager.model_bindings(lambda: False)
        assert len(bindings) == 2, (manager.catalog(), [manager.discover(name) for name in servers])
        assert len({row.model_name for row in bindings}) == 2
        assert {row.source_name for row in bindings} == {"alpha", "beta"}

        from iris.infrastructure.speak_capability import bind_live_control_surface
        from iris.system.control_surface import ActionRegistry
        from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta

        registry = ActionRegistry()
        registry.set_human_confirm(lambda _spec, _preview: False)
        bind_live_control_surface(SimpleNamespace(registry=registry, booting=False))
        try:
            with bind_host_tool_call_meta(
                tool_call_id="deny-call",
                execution_context=ExecutionContext(session_id="deny-session"),
            ):
                denied = manager.invoke_binding(bindings[0], {})
            assert denied["error_code"] == "approval_denied"
            assert not paths[bindings[0].source_name][1].exists()
        finally:
            bind_live_control_surface(None)

        schema = {"type": "object"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            same = list(pool.map(
                lambda _: manager.call_tool("alpha", "same", {}, expected_schema=schema),
                range(2),
            ))
        assert all(row["status"] == "ok" for row in same), same
        assert not paths["alpha"][0].with_suffix(".overlap").exists()

        with ThreadPoolExecutor(max_workers=2) as pool:
            distinct = list(pool.map(
                lambda name: manager.call_tool(name, "same", {}, expected_schema=schema),
                ("alpha", "beta"),
            ))
        assert {row["result"]["structuredContent"]["marker"] for row in distinct} == {"alpha", "beta"}

        # Every operation owns a fresh SDK/server process, so a killed prior process cannot poison the next call.
        again = manager.call_tool("beta", "same", {}, expected_schema=schema)
        assert again["status"] == "ok" and paths["beta"][1].read_text() == "2"

        flaky = root / "flaky.py"
        flaky.write_text(FLAKY, encoding="utf-8")
        sentinel = root / "flaky.started"
        manager.register("flaky", {"command": sys.executable, "args": [str(flaky), str(sentinel)]})
        assert manager.discover("flaky")["status"] == "connection_failed"
        assert manager.discover("flaky")["status"] == "connected"

        before = int(paths["alpha"][1].read_text())
        timed = manager.call_tool("alpha", "same", {}, expected_schema=schema, timeout=0.05)
        assert timed == {"status": "timeout", "execution_uncertain": True}
        assert int(paths["alpha"][1].read_text()) in {before, before + 1}
    print("ok: MCP multi-server reconnect and serialization")


if __name__ == "__main__":
    main()
