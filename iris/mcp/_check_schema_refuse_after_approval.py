"""FRC-04B: after human approve, schema fingerprint mismatch must refuse.

python -m iris.mcp._check_schema_refuse_after_approval
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from iris.infrastructure.speak_capability import bind_live_control_surface
from iris.mcp.native_manager import NativeMCPManager
from iris.system.control_surface import ActionRegistry
from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta


def check_schema_refuse_after_approval(home: Path | None = None) -> None:
    root = home
    cleanup = None
    if root is None:
        cleanup = tempfile.TemporaryDirectory(prefix="iris-frc04b-schema-")
        root = Path(cleanup.name)
    try:
        manager = NativeMCPManager(home=root)
        manager.register("schema-server", {
            "url": "https://mcp.test/schema", "enabled": True, "model_enabled": True,
        })
        discovered = {"status": "connected", "tools": [{
            "name": "echo", "description": "Echo", "inputSchema": {"type": "object"},
        }]}
        with patch.object(manager, "discover", return_value=discovered):
            bindings = manager.model_bindings(lambda: False)
        assert len(bindings) == 1, bindings
        binding = bindings[0]
        registry = ActionRegistry()
        try:
            with bind_host_tool_call_meta(
                tool_call_id="schema-call",
                execution_context=ExecutionContext(session_id="schema-session"),
            ):
                bind_live_control_surface(SimpleNamespace(registry=registry, booting=False))
                registry.set_human_confirm(lambda _spec, _preview: True)

                def refuse_changed_schema(_config, _transport, _timeout, _cancelled, request):
                    assert request["operation"] == "call_tool"
                    assert request["schema_fingerprint"] == binding.schema_fingerprint
                    return {"status": "schema_changed"}

                with patch.object(manager, "_run_sdk", side_effect=refuse_changed_schema) as sdk:
                    result = manager.invoke_binding(binding, {})
                assert result["ok"] is False, result
                assert result["error_code"] == "schema_changed", result
                assert result.get("execution_uncertain") is False, result
                sdk.assert_called_once()
        finally:
            bind_live_control_surface(None)
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def main() -> None:
    check_schema_refuse_after_approval()
    print("ok: schema fingerprint refused after approval")


if __name__ == "__main__":
    main()
