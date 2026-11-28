"""Native connections.status — non-secret MCP/Gateway posture (Hermes manage_connections)."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result

# Never forward these key names to the model (Boundary Discipline).
_SECRET_KEY_FRAGMENTS = (
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "bearer",
    "credential",
    "headers",
    "env",
)


def _scrub_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep name / connected / last_error only — drop anything secret-looking."""
    name = str(row.get("name") or "").strip() or "(unnamed)"
    ok = bool(row.get("ok"))
    enabled = bool(row.get("enabled", True))
    detail = str(row.get("detail") or row.get("last_error") or "").strip()
    kind = str(row.get("kind") or "").strip()
    out: dict[str, Any] = {
        "name": name,
        "connected": bool(ok and enabled),
        "enabled": enabled,
        "kind": kind or "unknown",
        "last_error": "" if ok else detail[:200],
    }
    # Refuse accidental secret leakage if probe ever grows fields.
    for key in list(out):
        low = key.lower()
        if any(frag in low for frag in _SECRET_KEY_FRAGMENTS):
            out.pop(key, None)
    return out


def register_connections_actions(registry: ActionRegistry) -> None:
    def connections_status(_args: dict[str, Any]) -> dict[str, Any]:
        try:
            from iris.system.iris_agent_control_sync import (
                audit_all_mcp_servers,
                verify_install,
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("connections.status", f"status unavailable: {exc}"[:200])

        try:
            audited = audit_all_mcp_servers()
        except Exception as exc:  # noqa: BLE001
            audited = []
            audit_error = str(exc)[:200]
        else:
            audit_error = ""

        servers = [_scrub_row(row) if isinstance(row, dict) else _scrub_row({}) for row in audited]
        gateway: dict[str, Any] = {
            "speak_tools_path": True,
            "http_gateway": "retired",
            "reconnect": "disk_verify_only",
        }
        try:
            report = verify_install()
            gateway["speak_tools_ok"] = bool(report.mcp_installed and report.ok)
            gateway["mobile_mcp_installed"] = bool(report.mobile_mcp_installed)
            if report.errors:
                gateway["last_error"] = str(report.errors[0])[:200]
        except Exception as exc:  # noqa: BLE001
            gateway["speak_tools_ok"] = False
            gateway["last_error"] = str(exc)[:200]

        payload: dict[str, Any] = {
            "mcp_servers": servers,
            "gateway": gateway,
            "count": len(servers),
        }
        if audit_error:
            payload["audit_error"] = audit_error
        return ok_result("connections.status", payload)

    registry.register(
        "connections.status",
        connections_status,
        summary=(
            "Non-secret MCP/Gateway status (name, connected, last_error). "
            "Never returns tokens or API keys. Hermes manage_connections absorb."
        ),
        risk="low",
        confirm_required=False,
    )
