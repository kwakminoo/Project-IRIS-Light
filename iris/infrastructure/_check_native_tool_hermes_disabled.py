"""Product sidecars must never dispatch through the original registry."""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

from iris.engine import _sidecar_main as sidecar
from iris.infrastructure.absorbed_tool_aliases import (
    INTERNAL_ALIASES,
    model_names,
    strip_only_names,
)


def _simulate_product_install() -> tuple[object, list[str], object]:
    hermes_hits: list[str] = []

    def hermes_dispatch(name: str, args: dict, **_kwargs: object) -> str:
        hermes_hits.append(str(name))
        return "HERMES_RAN"

    fake = SimpleNamespace(
        register=lambda **_kwargs: None,
        dispatch=hermes_dispatch,
    )
    tools_mod = types.ModuleType("tools")
    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = fake
    tools_mod.registry = registry_mod
    model_tools_mod = types.ModuleType("model_tools")
    model_tools_mod.handle_function_call = lambda *_a, **_k: "HERMES"
    mcp_mod = types.ModuleType("tools.mcp_tool_agent")
    mcp_mod.refresh_agent_mcp_tools = lambda *_a, **_k: set()

    prev = {
        key: sys.modules.get(key)
        for key in ("tools", "tools.registry", "model_tools", "tools.mcp_tool_agent")
    }
    sys.modules["tools"] = tools_mod
    sys.modules["tools.registry"] = registry_mod
    sys.modules["model_tools"] = model_tools_mod
    sys.modules["tools.mcp_tool_agent"] = mcp_mod

    agent = SimpleNamespace(tools=[], valid_tool_names=set())
    original_request = sidecar._request_native_tool
    sidecar._request_native_tool = lambda *_a, **_k: '{"ok": true}'
    try:
        sidecar._install_iris_engine_tools(
            agent,
            surface="home",
            bridge_context={
                "turn_id": "turn-1",
                "session_id": "session-1",
                "workspace_id": "workspace-1",
            },
        )
        return agent, hermes_hits, fake
    finally:
        sidecar._request_native_tool = original_request
        for key, value in prev.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


def main() -> None:
    agent, hermes_hits, registry = _simulate_product_install()
    assert getattr(agent, "_iris_native_tool_bindings", None) is not None

    absorbed = sorted(model_names())[0]
    strip = sorted(strip_only_names())[0]
    alias = next(iter(INTERNAL_ALIASES))

    for name in (absorbed, strip, alias, "delegate_task", "unregistered_original_tool"):
        result = registry.dispatch(name, {"probe": True})
        payload = json.loads(result)
        assert payload.get("ok") is False, (name, result)
        assert payload.get("error") == "TOOL_NOT_AVAILABLE", (name, result)
        assert payload.get("tool_name") == name, (name, result)

    assert hermes_hits == [], hermes_hits
    print(
        "native_tool_hermes_disabled ok",
        f"blocked={absorbed},{strip},{alias}",
    )


if __name__ == "__main__":
    main()
