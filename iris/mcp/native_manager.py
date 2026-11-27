"""Use explicitly registered MCP servers through the installed Owned Core SDK."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

_HTTP_TRANSPORTS = {
    "http": "streamable_http",
    "streamable-http": "streamable_http",
    "streamable_http": "streamable_http",
    "sse": "sse",
}
_MAX_ITEMS = 200
_MAX_RESPONSE_BYTES = 2_000_000
_TOOL_COMPONENT = re.compile(r"[a-zA-Z0-9_.-]{1,128}\Z")
_LOCAL_HTTP_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_SDK_ENV = frozenset({
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
})


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MCPToolBinding:
    model_name: str
    canonical_action: str
    source_name: str
    external_name: str
    input_schema: dict[str, Any]
    config_fingerprint: str
    schema_fingerprint: str
    connection_generation: str
    fingerprint: str
    source: str = "mcp"
    risk: str = "high"
    permission_scope: str = "once"

    @property
    def description(self) -> str:
        return f"Run {self.external_name} from the connected MCP service {self.source_name}."

    def model_projection(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name, "canonical_action": self.canonical_action,
            "description": self.description, "input_schema": self.input_schema,
            "fingerprint": self.fingerprint, "source": self.source, "source_name": self.source_name,
        }


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
            or type(config.get("model_enabled", False)) is not bool
            or _config_status({**config, "enabled": True})[1] != "configured"
        ):
            raise ValueError("MCP 서버 설정 형식이 올바르지 않습니다")
        with edit_mcp_servers(self._home) as servers:
            if name in servers:
                raise RuntimeError("같은 이름의 MCP 서버가 이미 등록되어 있습니다")
            servers[name] = {**config, "model_revision": uuid4().hex} if config.get("model_enabled") else config

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
            if config.get("enabled", True) is not enabled:
                config.update(enabled=enabled, model_revision=uuid4().hex)

    def model_bindings(self, cancelled: Callable[[], bool], *, gateway: bool = False) -> tuple[MCPToolBinding, ...]:
        bindings: list[MCPToolBinding] = []
        deadline = monotonic() + 12
        for server, config in self._servers().items():
            remaining = deadline - monotonic()
            if remaining <= 0 or cancelled() or len(bindings) >= _MAX_ITEMS:
                break
            if (not isinstance(server, str) or not _TOOL_COMPONENT.fullmatch(server)
                    or _config_status(config)[1] != "configured" or config.get("model_enabled") is not True
                    or (gateway and config.get("gateway_enabled") is not True)):
                continue
            config_id = _binding_config_fingerprint(config)
            if not config_id:
                continue
            found = self.discover(server, timeout=min(5, remaining), cancelled=cancelled,
                                  expected_config=config_id)
            if found.get("status") != "connected" or self._binding_status(server, config_id, gateway=gateway):
                continue
            generation = uuid4().hex
            tools = found.get("tools", [])
            for tool in tools:
                name, schema = tool.get("name"), tool.get("inputSchema")
                if (not isinstance(name, str) or not _TOOL_COMPONENT.fullmatch(name)
                        or not isinstance(schema, dict) or schema.get("type") != "object"
                        or sum(row.get("name") == name for row in tools) != 1):
                    continue
                stable_id = fingerprint([server, name])
                slug = lambda value, limit: re.sub(r"[^a-z0-9_]", "_", value.lower())[:limit]
                model_name = f"mcp_{slug(server, 16)}_{slug(name, 28)}_{stable_id[:12]}"
                schema_id = fingerprint(schema)
                bindings.append(MCPToolBinding(
                    model_name, f"mcp:{stable_id}", server, name, schema, config_id, schema_id,
                    generation, fingerprint([stable_id, config_id, schema_id, generation]),
                ))
        return tuple(bindings[:_MAX_ITEMS])

    def _binding_status(self, server: str, expected: str, *, gateway: bool) -> str:
        config = self._servers().get(server)
        if config is None:
            return "not_registered"
        _, status = _config_status(config)
        if status != "configured":
            return status
        if config.get("model_enabled") is not True or (gateway and config.get("gateway_enabled") is not True):
            return "permission_denied"
        return "" if _binding_config_fingerprint(config) == expected else "config_changed"

    def invoke_binding(self, binding: MCPToolBinding, arguments: Any, *, human_confirm=None) -> dict[str, Any]:
        from iris.infrastructure.speak_capability import _live_control_surface
        from iris.system.control_surface import ActionSpec
        from iris.system.execution_context import host_execution_context, host_tool_cancelled
        from iris.system.execution_policy import TOOL_OUTPUT_BEGIN, check_action_approval
        from iris.system.request_approval import default_approval_ledger

        def rejected(code: str) -> dict[str, Any]:
            return {"ok": False, "error": code, "error_code": code, "retryable": False}

        ctx = host_execution_context()
        if ctx is None or not ctx.effective_session_id() or not ctx.tool_call_id:
            return rejected("permission_denied")
        gateway = ctx.surface == "gateway"
        if gateway and (ctx.permission_scope != "gateway.mcp" or human_confirm is None):
            return rejected("permission_denied")
        status = self._binding_status(binding.source_name, binding.config_fingerprint, gateway=gateway)
        if status:
            return rejected(status)
        if not isinstance(arguments, dict):
            return rejected("invalid_arguments")
        try:
            preview = json.dumps(arguments, ensure_ascii=True, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return rejected("invalid_arguments")
        # The existing confirmation HUD displays the full argument preview within this limit.
        if len(preview) > 540:
            return rejected("approval_preview_limit")
        if not gateway:
            registry = getattr(_live_control_surface(), "registry", None)
            human_confirm = registry.ask_human if registry else None
        spec = ActionSpec(name="MCP", summary=f"{binding.source_name} → {binding.external_name}",
                          risk=binding.risk, confirm_required=True)
        decision = check_action_approval(spec, {"text": preview}, human_confirm)
        if not decision.allowed:
            return rejected("approval_required" if decision.reason == "human confirm required" else "approval_denied")
        if host_tool_cancelled():
            return rejected("cancelled")
        status = self._binding_status(binding.source_name, binding.config_fingerprint, gateway=gateway)
        if status:
            return rejected(status)
        ledger = default_approval_ledger()
        scope = {"fingerprint": fingerprint([binding.fingerprint, preview]),
                 "session_id": ctx.effective_session_id(), "workspace_id": ctx.workspace_id,
                 "tool_call_id": ctx.tool_call_id}
        approval = ledger.grant(**scope, approval_scope=binding.permission_scope)
        allowed, _ = ledger.consume(**scope, request_id=approval.request_id)
        if not allowed:
            return rejected("approval_invalid")
        result = self.call_tool(binding.source_name, binding.external_name, arguments,
                                expected_schema=binding.input_schema, expected_config=binding.config_fingerprint,
                                cancelled=host_tool_cancelled)
        status = result["status"]
        out = {"ok": status == "ok", "status": status, "source": binding.source_name}
        if "result" in result:
            out["data"] = result["result"]
            out["data_boundary"] = TOOL_OUTPUT_BEGIN
        if status != "ok":
            out.update(error=status, error_code=status, retryable=False,
                       execution_uncertain=result.get("execution_uncertain", False))
        return out

    def discover(
        self, name: str, *, timeout: float = 20, cancelled: Callable[[], bool] | None = None,
        expected_config: str = "",
    ) -> dict[str, Any]:
        """Open a fresh connection and read supported lists. A retry opens a new connection."""
        return self._request(name, {"operation": "discover"}, timeout, cancelled, expected_config)

    def call_tool(
        self, server: str, name: str, arguments: dict[str, Any], *,
        expected_schema: dict[str, Any] | None = None, expected_config: str = "",
        timeout: float = 20, cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return self._request(server, {
            "operation": "call_tool", "name": name, "arguments": arguments,
            "schema_fingerprint": fingerprint(expected_schema) if expected_schema is not None else "",
        }, timeout, cancelled, expected_config)

    def read_resource(
        self, server: str, uri: str, *, timeout: float = 20,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return self._request(server, {"operation": "read_resource", "name": uri}, timeout, cancelled)

    def get_prompt(
        self, server: str, name: str, arguments: dict[str, str], *, timeout: float = 20,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if not _string_map(arguments):
            return {"status": "invalid_arguments"}
        return self._request(server, {"operation": "get_prompt", "name": name, "arguments": arguments},
                             timeout, cancelled)

    def _request(
        self, name: str, request: dict, timeout: float, cancelled: Callable[[], bool] | None,
        expected_config: str = "",
    ) -> dict[str, Any]:
        from iris.system.iris_agent_control_sync import iris_agent_config_path, parse_mcp_servers_config

        path = iris_agent_config_path(self._home).absolute()
        try:
            config_bytes = path.read_bytes()
        except OSError:
            return {"status": "not_registered"}
        servers = parse_mcp_servers_config(config_bytes)
        if name not in servers:
            return {"status": "not_registered"}
        transport, status = _config_status(servers[name])
        if status != "configured":
            return {"status": status}
        if not math.isfinite(timeout) or not 0 < timeout <= 120:
            return {"status": "invalid_timeout"}
        if cancelled is not None and cancelled():
            return {"status": "cancelled"}
        config = servers[name]
        resolved = _resolve_config_command(config)
        if transport == "stdio" and not resolved:
            return {"status": "command_unavailable"}
        if expected_config and expected_config != _binding_config_fingerprint(config, resolved=resolved):
            return {"status": "config_changed"}
        request.update(config_path=str(path), config_digest=hashlib.sha256(config_bytes).hexdigest())
        return self._run_sdk({**config, "command": resolved} if resolved else config,
                             transport, timeout, cancelled, request)

    @staticmethod
    def _run_sdk(config: dict, transport: str, timeout: float, cancelled: Callable[[], bool] | None,
                 request: dict) -> dict:
        from iris.engine._home import engine_python
        from iris.engine.types import EngineHome
        from iris.infrastructure.agent_runtime import iris_agent_home
        from iris.system.execution_runtime import _kill_process_tree
        from iris.system.win_subprocess import no_window_kwargs

        python = engine_python(EngineHome(iris_agent_home()))
        if python is None:
            return {"status": "runtime_unavailable"}
        fields = ("command", "args", "env", "cwd") if transport == "stdio" else ("url", "headers")
        try:
            payload = json.dumps({
                **request, "config": {key: config[key] for key in fields if key in config},
                "transport": transport, "timeout": timeout,
            }, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            return {"status": "invalid_arguments"}
        if len(payload) > _MAX_RESPONSE_BYTES:
            return {"status": "request_limit"}
        invoking = request["operation"] != "discover"
        try:
            proc = subprocess.Popen(
                [str(python), "-I", "-X", "utf8", str(Path(__file__).resolve())],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={key: value for key, value in os.environ.items() if key.upper() in _SDK_ENV},
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
                        return {"status": "cancelled", "execution_uncertain": invoking}
                    if monotonic() >= deadline:
                        _kill_process_tree(proc)
                        return {"status": "timeout", "execution_uncertain": invoking}
            if proc.returncode or not output or len(output) > _MAX_RESPONSE_BYTES:
                return {"status": "connection_failed", "execution_uncertain": invoking}
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
        if parsed.scheme == "http" and parsed.hostname not in _LOCAL_HTTP_HOSTS:
            return transport, "insecure_url"
        _ = parsed.port
    except ValueError:
        return transport, "invalid_config"
    return _HTTP_TRANSPORTS[transport], "configured"


def _resolve_config_command(config: dict) -> str:
    from iris.system.executable_resolve import resolve_executable

    return (resolve_executable(config["command"]) or "") if config.get("command") else ""


def _binding_config_fingerprint(config: dict, *, resolved: str | None = None) -> str:
    try:
        command = _resolve_config_command(config) if resolved is None else resolved
        return fingerprint([config, command]) if not config.get("command") or command else ""
    except (TypeError, ValueError):
        return ""


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


def _is_current(request: dict) -> bool:
    try:
        return hashlib.sha256(Path(request["config_path"]).read_bytes()).hexdigest() == request["config_digest"]
    except OSError:
        return False


def _validate_arguments(schema: dict, arguments: Any) -> str:
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for
    from referencing import Registry
    from referencing.exceptions import Unresolvable

    if not isinstance(arguments, dict):
        return "invalid_arguments"
    try:
        validator = validator_for(schema)
        validator.check_schema(schema)
        # An installed server's input schema cannot initiate network/file fetches.
        if not validator(schema, registry=Registry()).is_valid(arguments):
            return "invalid_arguments"
    except (SchemaError, ValueError, TypeError, RecursionError, Unresolvable):
        return "invalid_schema"
    return ""


async def _operate(request: dict) -> dict:
    from contextlib import AsyncExitStack

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.shared.exceptions import MCPError

    config, transport, timeout = request["config"], request["transport"], request["timeout"]
    if not _is_current(request):
        return {"status": "config_changed"}
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
        operation = request["operation"]
        if operation != "discover":
            name = request["name"]
            if not isinstance(name, str) or not name.strip():
                return {"status": "invalid_arguments"}
            if operation == "call_tool":
                if getattr(capabilities, "tools", None) is None:
                    return {"status": "tool_unavailable"}
                tools = await _list_all(session.list_tools, "tools")
                matches = [row["inputSchema"] for row in tools if row.get("name") == name]
                if len(matches) != 1:
                    return {"status": "tool_unavailable"}
                schema = matches[0]
                expected = request["schema_fingerprint"]
                if expected and fingerprint(schema) != expected:
                    return {"status": "schema_changed"}
                invalid = _validate_arguments(schema, request["arguments"])
                if invalid:
                    return {"status": invalid}
            if not _is_current(request):
                return {"status": "config_changed"}
            try:
                if operation == "call_tool":
                    reply = await session.call_tool(name, request["arguments"])
                elif operation == "read_resource":
                    reply = await session.read_resource(name)
                else:
                    reply = await session.get_prompt(name, request["arguments"])
            except MCPError:
                return {"status": "mcp_error", "execution_uncertain": True}
            if getattr(reply, "is_error", False):
                status = "tool_error"
            elif getattr(reply, "request_state", None) is not None:
                return {"status": "additional_input_required", "execution_uncertain": True}
            else:
                status = "ok"
            return {"status": status, "result": reply.model_dump(mode="json", by_alias=True, exclude_none=True)}
        result = {"status": "connected", "capabilities": capabilities.model_dump(mode="json", exclude_none=True)}
        for key in ("tools", "resources", "prompts"):
            method = getattr(session, f"list_{key}")
            result[key] = await _list_all(method, key) if getattr(capabilities, key, None) is not None else []
        return result


if __name__ == "__main__":
    request = {}
    try:
        request = json.load(sys.stdin)
        response = asyncio.run(_operate(request))
    except TimeoutError:
        response = {"status": "timeout"}
    except ImportError:
        response = {"status": "sdk_unavailable"}
    except Exception:
        response = {"status": "connection_failed"}
    data = json.dumps(response)
    if len(data) > _MAX_RESPONSE_BYTES:
        response = {"status": "response_limit"}
    if response["status"] in {"timeout", "connection_failed", "response_limit"}:
        response["execution_uncertain"] = request.get("operation", "discover") != "discover"
    print(json.dumps(response))
