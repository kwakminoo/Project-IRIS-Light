"""Read one MCP App resource from an explicitly named Hermes stdio server."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from iris.apps.directory import AppDirectory
from iris.engine.app_ui import materialize_mcp_app_resource
from iris.system.github_extension_install import probe_mcp
from iris.system.iris_agent_control_sync import load_mcp_servers_config

MCP_APP_RESOURCE_TIMEOUT = 2.5
# Directory + netloc + scan share one wall budget so the UI thread cannot hang.
MCP_APP_RESOLVE_BUDGET = MCP_APP_RESOURCE_TIMEOUT * 2


def read_configured_mcp_resource(
    server_name: str,
    uri: str,
    *,
    home: Path | None = None,
) -> dict[str, Any] | None:
    """Initialize one configured stdio server and return resources/read result."""
    name = (server_name or "").strip()
    if not name or not (uri or "").lower().startswith("ui://"):
        return None
    config = load_mcp_servers_config(home).get(name)
    if not isinstance(config, dict) or config.get("enabled") is False:
        return None
    transport = str(config.get("transport") or config.get("type") or "stdio").lower()
    if transport not in ("", "stdio") or config.get("url"):
        return None
    command = str(config.get("command") or "").strip()
    args = config.get("args")
    env = config.get("env")
    if not command or (args is not None and not isinstance(args, list)):
        return None
    if env is not None and not isinstance(env, dict):
        return None
    child_env = {str(key): str(value) for key, value in (env or {}).items()}
    report = probe_mcp(
        command,
        [str(arg) for arg in (args or [])],
        child_env,
        cwd=str(config.get("cwd") or ""),
        startup_timeout=MCP_APP_RESOURCE_TIMEOUT,
        rpc_timeout=MCP_APP_RESOURCE_TIMEOUT,
        secrets=child_env,
        resource_uri=uri,
    )
    resource = report.get("resource") if report.get("ok") else None
    return resource if isinstance(resource, dict) else None


def _directory_for_home(home: Path | None) -> AppDirectory:
    if home is None:
        return AppDirectory()
    flat = home / "directory.json"
    if flat.is_file():
        return AppDirectory(flat)
    return AppDirectory(home / "apps" / "directory.json")


def _enabled_stdio_servers(home: Path | None) -> list[str]:
    names: list[str] = []
    for name, config in load_mcp_servers_config(home).items():
        key = str(name or "").strip()
        if not key or not isinstance(config, dict) or config.get("enabled") is False:
            continue
        transport = str(config.get("transport") or config.get("type") or "stdio").lower()
        if transport not in ("", "stdio") or config.get("url"):
            continue
        if not str(config.get("command") or "").strip():
            continue
        names.append(key)
    return names


def resolve_ui_resource(
    uri: str,
    *,
    home: Path | None = None,
) -> dict[str, Any] | None:
    """Resolve ``ui://`` to an MCP resources/read dict without a caller-given server.

    Prefer App Directory ``server_name``, then netloc match against enabled stdio
    servers, then scan enabled stdio servers until materialize accepts one.
    """
    raw = (uri or "").strip()
    if not raw.lower().startswith("ui://"):
        return None
    deadline = time.monotonic() + MCP_APP_RESOLVE_BUDGET

    for entry in _directory_for_home(home).list():
        if entry.resource_uri != raw:
            continue
        server_name = (entry.server_name or "").strip()
        if not server_name:
            continue
        if time.monotonic() >= deadline:
            return None
        resource = read_configured_mcp_resource(server_name, raw, home=home)
        if resource is not None:
            return resource

    netloc = (urlparse(raw).netloc or "").strip()
    if netloc and netloc in _enabled_stdio_servers(home):
        if time.monotonic() >= deadline:
            return None
        resource = read_configured_mcp_resource(netloc, raw, home=home)
        if resource is not None:
            return resource

    probe_cache = Path(home) / ".iris-app-ui-probe" if home is not None else None
    for server_name in _enabled_stdio_servers(home):
        if time.monotonic() >= deadline:
            return None
        if netloc and server_name == netloc:
            continue
        resource = read_configured_mcp_resource(server_name, raw, home=home)
        if resource is None:
            continue
        if materialize_mcp_app_resource(raw, resource, cache_dir=probe_cache) is not None:
            return resource
    return None
