"""Product sidecars must never dispatch through the original registry.

Gate B / R-NAT-FIG09 negatives:
- Hermes original names stay blocked (apply_patch, patch; clarify absorbed → native)
- unregistered / inactive invokes are refused
- confirm_required cannot be self-approved by model confirm:true alone
"""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

from iris.infrastructure.absorbed_tool_aliases import (
    INTERNAL_ALIASES,
    model_names,
    resolve_action,
    strip_only_names,
)
from iris.infrastructure.agent_tool_registry import invoke_agent_tool
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    SpeakTools,
    engine_tool_schemas,
)
from iris.system.control_surface import ActionSpec
from iris.system.execution_policy import check_action_approval
from iris.engine import _sidecar_main as sidecar

# Gate B pinned Hermes originals (must stay TOOL_NOT_AVAILABLE on product install).
# clarify/delegate_task absorbed (FFC-03 Unit 4c/4d); keep apply_patch/patch blocked.
_MUST_BLOCK_HERMES = ("apply_patch", "patch")


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


def _assert_hermes_registry_blocked(registry: object, name: str) -> None:
    result = registry.dispatch(name, {"probe": True})  # type: ignore[attr-defined]
    payload = json.loads(result)
    assert payload.get("ok") is False, (name, result)
    assert payload.get("error") == "TOOL_NOT_AVAILABLE", (name, result)
    assert payload.get("tool_name") == name, (name, result)


def _check_unregistered_and_inactive() -> None:
    """Speak / agent registry / strip-only (inactive) must refuse, not run."""
    class _Surf:
        def invoke(self, action: str, args: dict) -> dict | None:
            raise AssertionError(f"unregistered must not hit surface: {action}")

    tools = SpeakTools(PHASE4_ALLOWLIST, surface=_Surf())
    speak = tools.invoke("unregistered_gate_b_tool", {})
    assert speak.ok is False, speak
    assert "not_allowed" in (speak.error or ""), speak

    agent = invoke_agent_tool("unregistered_gate_b_tool", {})
    assert agent.get("ok") is False, agent
    assert "unknown tool" in str(agent.get("error") or ""), agent

    # Inactive Hermes strip-only umbrella: memory stays strip; memory_* Speak grants exist.
    assert "memory" in strip_only_names()
    assert resolve_action("memory", "home") is None
    home_names = {str(s["name"]) for s in engine_tool_schemas("home")}
    assert "memory" not in home_names
    assert "memory_search" in home_names
    assert "patch" not in home_names  # internal alias, not dual-emitted
    assert "execute_code" not in home_names  # INTERNAL_ALIAS → terminal; no dual schema
    assert resolve_action("execute_code", "home") == "shell.run"
    # Absorbed clarify / delegate_task / Unit 5 residuals are schema-emitted under Hermes names.
    assert "clarify" not in strip_only_names()
    assert resolve_action("clarify", "home") == "clarify.manage"
    assert "clarify" in home_names
    assert "delegate_task" not in strip_only_names()
    assert resolve_action("delegate_task", "home") == "delegate.manage"
    assert "delegate_task" in home_names
    assert "image_generate" not in strip_only_names()
    assert resolve_action("image_generate", "home") == "image.status"
    assert "image_generate" in home_names
    assert "text_to_speech" in home_names
    assert "cronjob_manage" in home_names
    assert "manage_connections" in home_names
    assert "computer_use" in home_names



def _check_approval_cannot_self_approve() -> None:
    """confirm_required + model confirm:true alone must stay denied."""
    spec = ActionSpec(
        name="email.send",
        summary="send",
        risk="high",
        confirm_required=True,
    )
    denied = check_action_approval(spec, {"confirm": True, "to": "a@b.c"}, None)
    assert denied.allowed is False, denied
    assert denied.reason == "human confirm required"


def main() -> None:
    agent, hermes_hits, registry = _simulate_product_install()
    assert getattr(agent, "_iris_native_tool_bindings", None) is not None

    absorbed = sorted(model_names())[0]
    strip = sorted(strip_only_names())[0]
    alias = next(iter(INTERNAL_ALIASES))

    for name in (absorbed, strip, alias, "delegate_task", "unregistered_original_tool"):
        _assert_hermes_registry_blocked(registry, name)

    # Gate B pin: named Hermes originals (not only "first of each set").
    for name in _MUST_BLOCK_HERMES:
        _assert_hermes_registry_blocked(registry, name)

    assert hermes_hits == [], hermes_hits

    _check_unregistered_and_inactive()
    _check_approval_cannot_self_approve()

    print(
        "native_tool_hermes_disabled ok",
        f"blocked={','.join(_MUST_BLOCK_HERMES)}",
        "gate_b=unregistered,inactive,approval_refuse",
    )


if __name__ == "__main__":
    main()
