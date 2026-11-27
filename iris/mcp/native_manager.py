"""Discover explicitly registered MCP servers with the installed Owned Core SDK."""

from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlsplit

_HTTP_TRANSPORTS = {
    "http": "streamable_http",
    "streamable-http": "streamable_http",
    "streamable_http": "streamable_http",
    "sse": "sse",
}
_MAX_ITEMS = 200
_MAX_RESPONSE_BYTES = 2_000_000


class NativeMCPManager:
    def __init__(self, *, home: Path | None = None) -> None:
        self._home = home

    def _servers(self) -> dict[str, Any]:
        from iris.system.iris_agent_control_sync import load_mcp_servers_config

        return load_mcp_servers_config(self._home)

    def catalog(self) -> list[dict[str, str]]:
        rows = []
        for name, config in self._servers().items():
            if not isinstance(name, str) or not name.strip():
                continue
            transport, status = _config_status(config)
            rows.append({"name": name, "status": status, "transport": transport})
        return rows

    def register(self, name: str, config: dict[str, Any]) -> None:
        from iris.system.iris_agent_control_sync import edit_mcp_servers

        if (
            not name.strip() or type(config.get("enabled", True)) is not bool
            or _config_status({**config, "enabled": True})[1] != "configured"
        ):
            raise ValueError("MCP 서버 설정 형식이 올바르지 않습니다")
        with edit_mcp_servers(self._home) as servers:
            if name in servers:
                raise RuntimeError("같은 이름의 MCP 서버가 이미 등록되어 있습니다")
            servers[name] = config

    def set_enabled(self, name: str, enabled: bool) -> None:
        from iris.system.iris_agent_control_sync import edit_mcp_servers

        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        with edit_mcp_servers(self._home) as servers:
            config = servers.get(name)
            if not isinstance(config, dict):
                raise ValueError("등록된 MCP 서버 설정을 찾을 수 없습니다")
            if enabled and _config_status({**config, "enabled": True})[1] != "configured":
                raise ValueError("MCP 서버 설정 형식이 올바르지 않습니다")
            config["enabled"] = enabled

    def discover(
        self, name: str, *, timeout: float = 20, cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Open a fresh connection and read supported lists. A retry opens a new connection."""
        servers = self._servers()
        if name not in servers:
            return {"status": "not_registered"}
        transport, status = _config_status(servers[name])
        if status != "configured":
            return {"status": status}
        if not math.isfinite(timeout) or not 0 < timeout <= 120:
            return {"status": "invalid_timeout"}
        if cancelled is not None and cancelled():
            return {"status": "cancelled"}
        return self._run_sdk(servers[name], transport, timeout, cancelled)

    @staticmethod
    def _run_sdk(config: dict, transport: str, timeout: float, cancelled: Callable[[], bool] | None) -> dict:
        from iris.engine._home import engine_python
        from iris.engine.types import EngineHome
        from iris.infrastructure.agent_runtime import iris_agent_home
        from iris.system.execution_runtime import _kill_process_tree
        from iris.system.executable_resolve import resolve_executable
        from iris.system.win_subprocess import no_window_kwargs

        python = engine_python(EngineHome(iris_agent_home()))
        if python is None:
            return {"status": "runtime_unavailable"}
        config = dict(config)
        if transport == "stdio":
            command = resolve_executable(config["command"])
            if not command:
                return {"status": "command_unavailable"}
            config["command"] = command
        fields = ("command", "args", "env", "cwd") if transport == "stdio" else ("url", "headers")
        payload = json.dumps({
            "config": {key: config[key] for key in fields if key in config},
            "transport": transport, "timeout": timeout,
        }).encode("utf-8")
        try:
            proc = subprocess.Popen(
                [str(python), "-I", "-X", "utf8", str(Path(__file__).resolve())],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=sys.platform != "win32", **no_window_kwargs(),
            )
        except OSError:
            return {"status": "runtime_unavailable"}
        with proc:
            deadline = monotonic() + timeout + 3
            incoming = payload
            while True:
                try:
                    output, _ = proc.communicate(input=incoming, timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    incoming = None
                    if cancelled is not None and cancelled():
                        _kill_process_tree(proc)
                        return {"status": "cancelled"}
                    if monotonic() >= deadline:
                        _kill_process_tree(proc)
                        return {"status": "timeout"}
            if proc.returncode or not output or len(output) > _MAX_RESPONSE_BYTES:
                return {"status": "connection_failed"}
            try:
                result = json.loads(output)
            except (ValueError, UnicodeError):
                return {"status": "invalid_response"}
            return result if isinstance(result, dict) else {"status": "invalid_response"}


def _config_status(config: Any) -> tuple[str, str]:
    if not isinstance(config, dict):
        return "", "invalid_config"
    command, url = config.get("command"), config.get("url")
    requested = config.get("transport") or config.get("type") or ("http" if url else "stdio")
    if not isinstance(requested, str):
        return "", "invalid_config"
    transport = requested.strip().lower()
    if config.get("enabled") is False:
        return transport, "disabled"
    if "enabled" in config and type(config["enabled"]) is not bool:
        return transport, "invalid_config"
    if transport not in _HTTP_TRANSPORTS and transport != "stdio":
        return transport, "unsupported_transport"
    if bool(command) == bool(url) or (transport == "stdio") != bool(command):
        return "", "invalid_config"
    if transport == "stdio":
        args, env, cwd = config.get("args", []), config.get("env", {}), config.get("cwd", "")
        if (
            not isinstance(command, str) or not command.strip() or "\0" in command
            or not isinstance(args, list) or any(not isinstance(arg, str) or "\0" in arg for arg in args)
            or not _string_map(env) or not isinstance(cwd, str) or "\0" in cwd
        ):
            return transport, "invalid_config"
        return transport, "configured"
    if config.get("auth") or config.get("oauth"):
        return transport, "unsupported_auth"
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            parsed is None or parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.fragment or not _string_map(config.get("headers", {}))
        ):
            return transport, "invalid_config"
        _ = parsed.port
    except ValueError:
        return transport, "invalid_config"
    return _HTTP_TRANSPORTS[transport], "configured"


def _string_map(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) and "\0" not in key + item
        for key, item in value.items()
    )


async def _list_all(method, key):
    from mcp.types import PaginatedRequestParams

    rows, previous = [], set()
    cursor = None
    for _ in range(16):
        result = await method(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
        rows.extend(row.model_dump(mode="json", by_alias=True, exclude_none=True) for row in getattr(result, key))
        cursor = getattr(result, "next_cursor", None) or getattr(result, "nextCursor", None)
        if len(rows) > _MAX_ITEMS or cursor in previous:
            raise ValueError("MCP discovery limit exceeded")
        if not cursor:
            return rows
        previous.add(cursor)
    raise ValueError("MCP pagination limit exceeded")


async def _discover(request: dict) -> dict:
    from contextlib import AsyncExitStack

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.shared.exceptions import MCPError

    config, transport, timeout = request["config"], request["transport"], request["timeout"]
    async with asyncio.timeout(timeout), AsyncExitStack() as stack:
        if transport == "stdio":
            if config.get("cwd"):
                config["cwd"] = Path(config["cwd"]).expanduser()
            streams = await stack.enter_async_context(stdio_client(StdioServerParameters(**config)))
        elif transport == "sse":
            from httpx2 import AsyncClient
            from mcp.client.sse import sse_client

            def client_factory(**kwargs):
                return AsyncClient(**kwargs, follow_redirects=False, trust_env=False)

            streams = await stack.enter_async_context(sse_client(
                config["url"], headers=config.get("headers"), httpx_client_factory=client_factory,
            ))
        else:
            from httpx2 import AsyncClient
            from mcp.client.streamable_http import streamable_http_client

            client = await stack.enter_async_context(AsyncClient(
                headers=config.get("headers"), follow_redirects=False, trust_env=False, timeout=timeout,
            ))
            streams = await stack.enter_async_context(streamable_http_client(config["url"], http_client=client))
        reader, writer, *_ = streams
        session = await stack.enter_async_context(ClientSession(reader, writer))
        try:
            initialize = await session.initialize()
        except MCPError as exc:
            if exc.error.code not in (-32022, -32601) or not hasattr(session, "discover"):
                raise
            initialize = await session.discover()
        capabilities = initialize.capabilities
        result = {"status": "connected", "capabilities": capabilities.model_dump(mode="json", exclude_none=True)}
        for key in ("tools", "resources", "prompts"):
            method = getattr(session, f"list_{key}")
            result[key] = await _list_all(method, key) if getattr(capabilities, key, None) is not None else []
        return result


if __name__ == "__main__":
    try:
        response = asyncio.run(_discover(json.load(sys.stdin)))
        data = json.dumps(response)
        if len(data) > _MAX_RESPONSE_BYTES:
            data = '{"status":"response_limit"}'
    except TimeoutError:
        data = '{"status":"timeout"}'
    except ImportError:
        data = '{"status":"sdk_unavailable"}'
    except Exception:
        data = '{"status":"connection_failed"}'
    print(data)
