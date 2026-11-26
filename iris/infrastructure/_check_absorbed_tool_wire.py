"""Wire: model-visible schemas use Hermes-familiar Iris names; install drops CORE."""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from types import SimpleNamespace

from iris.engine import _sidecar_main as sidecar
from iris.infrastructure.speak_capability import engine_tool_schemas, set_speak_surface

# Hermes CORE leftovers after Unit1 strip — must not survive Iris-only install.
_HERMES_CORE_LEFTOVERS = frozenset(
    {
        # process_manage absorbed → process.manage (U05); not a leftover
        # patch absorbed → apply_patch / project.apply_patch (U06); leftover name must not survive
        "patch",
        "vision_analyze",
        "image_generate",
        "skills_list",
        "skill_view",
        "skill_manage",
        "browser_exec",
        "browser_cdp",
        "browser_dialog",
        "browser_vault",
        "text_to_speech",
        "todo_list",
        "shell_run",
        "project_run",
        "project_write_file",
    }
)


def _names(surface: str) -> set[str]:
    return {str(row["name"]) for row in engine_tool_schemas(surface)}


def _fake_registry() -> SimpleNamespace:
    registered: list[str] = []

    def register(*, name: str, toolset: str, schema: dict, handler) -> None:
        registered.append(name)

    return SimpleNamespace(
        register=register,
        registered=registered,
        dispatch=lambda *_args, **_kwargs: "HERMES",
    )


def _simulate_install(surface: str, preload: list[str]) -> set[str]:
    """A hostile Hermes registry must not own schemas or dispatch after install."""
    fake = _fake_registry()
    tools_mod = types.ModuleType("tools")
    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = fake
    tools_mod.registry = registry_mod
    model_tools_mod = types.ModuleType("model_tools")
    model_tools_mod.handle_function_call = lambda *_args, **_kwargs: "HERMES"
    mcp_mod = types.ModuleType("tools.mcp_tool_agent")
    mcp_mod.refresh_agent_mcp_tools = lambda agent, **_kwargs: setattr(
        agent, "tools", [{"type": "function", "function": {"name": "memory"}}]
    )
    prev_tools = sys.modules.get("tools")
    prev_reg = sys.modules.get("tools.registry")
    prev_model_tools = sys.modules.get("model_tools")
    prev_mcp = sys.modules.get("tools.mcp_tool_agent")
    sys.modules["tools"] = tools_mod
    sys.modules["tools.registry"] = registry_mod
    sys.modules["model_tools"] = model_tools_mod
    sys.modules["tools.mcp_tool_agent"] = mcp_mod
    agent = SimpleNamespace(
        tools=[
            {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in preload
        ],
        valid_tool_names=set(preload),
    )
    native_calls: list[tuple[str, dict, dict]] = []
    original_request = sidecar._request_native_tool
    sidecar._request_native_tool = lambda name, args, **_kwargs: (
        native_calls.append((name, dict(args), dict(_kwargs))),
        '{"ok": true}',
    )[1]
    try:
        installed = sidecar._install_iris_engine_tools(
            agent,
            surface=surface,
            bridge_context={
                "turn_id": "turn-1",
                "session_id": "session-1",
                "workspace_id": "workspace-1",
            },
        )
        calls = {
            "terminal": {"command": "echo ok"},
            "process_manage": {"action": "list"},
            "write_file": {"path": "x", "content": "x"},
            "read_file": {"path": "x"},
            "search_files": {"query": "x"},
            "apply_patch": {"patch": "x"},
            "web_search": {"query": "x"},
            "web_extract": {"url": "https://example.test"},
        }
        results = {
            name: model_tools_mod.handle_function_call(
                name, args, tool_call_id=f"call-{name}"
            )
            for name, args in calls.items()
        }
        unavailable = model_tools_mod.handle_function_call("skills_list", {})
        mcp_mod.refresh_agent_mcp_tools(agent)
    finally:
        sidecar._request_native_tool = original_request
        if prev_tools is None:
            sys.modules.pop("tools", None)
        else:
            sys.modules["tools"] = prev_tools
        if prev_reg is None:
            sys.modules.pop("tools.registry", None)
        else:
            sys.modules["tools.registry"] = prev_reg
        if prev_model_tools is None:
            sys.modules.pop("model_tools", None)
        else:
            sys.modules["model_tools"] = prev_model_tools
        if prev_mcp is None:
            sys.modules.pop("tools.mcp_tool_agent", None)
        else:
            sys.modules["tools.mcp_tool_agent"] = prev_mcp
    visible = {
        str(row.get("function", {}).get("name") or "")
        for row in (agent.tools or [])
        if isinstance(row, dict)
    }
    installed_set = set(installed)
    # Progressive disclosure may hide the long tail behind tool_search; bindings
    # and valid_tool_names still cover every Iris model name.
    assert installed_set <= set(agent.valid_tool_names)
    assert "terminal" in visible
    assert visible - {"tool_search", "tool_describe", "tool_call"} <= installed_set
    assert fake.registered == [], "product install must not register into Hermes"
    assert all(result == '{"ok": true}' for result in results.values()), results
    expected_actions = {
        "terminal": "shell.run" if surface == "home" else "project.run",
        "process_manage": "process.manage",
        "write_file": "project.write_file",
        "read_file": "project.read_file",
        "search_files": "local.search_files",
        "apply_patch": "project.apply_patch",
        "web_search": "web.run_search",
        "web_extract": "web.run_extract",
    }
    assert [action for action, _args, _meta in native_calls] == [
        expected_actions[name] for name in calls
    ]
    for model_name, (_action, _args, meta) in zip(calls, native_calls):
        assert meta["model_tool_name"] == model_name, meta
        assert meta["schema_fingerprint"], meta
        assert meta["tool_call_id"] == f"call-{model_name}", meta
        assert meta["turn_id"] == "turn-1", meta
        assert meta["session_id"] == "session-1", meta
        assert meta["workspace_id"] == "workspace-1", meta
    assert "TOOL_NOT_AVAILABLE" in unavailable, unavailable
    assert "skills_list" not in visible
    assert "memory" not in visible, "late Hermes refresh replaced native snapshot"
    assert getattr(agent, "_skip_mcp_refresh", False) is True
    try:
        agent._iris_native_tool_bindings["terminal"] = "HERMES"
    except TypeError:
        pass
    else:
        raise AssertionError("native bindings must be immutable")
    return visible


def _check_native_transport_serialized() -> None:
    local = threading.local()
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()

    class _Stdin:
        def readline(self) -> str:
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            time.sleep(0.02)
            with state_lock:
                state["active"] -= 1
            req = local.request
            # Parent echoes correlation keys that _request_native_tool now requires.
            return json.dumps(
                {
                    "t": "tool_result",
                    "id": req["id"],
                    "tool_call_id": req.get("tool_call_id", ""),
                    "turn_id": req.get("turn_id", ""),
                    "session_id": req.get("session_id", ""),
                    "workspace_id": req.get("workspace_id", ""),
                    "result": {"ok": True},
                }
            )

    def emit(payload: dict) -> None:
        local.request = payload

    original_emit, original_stdin = sidecar._emit, sidecar.sys.stdin
    sidecar._emit, sidecar.sys.stdin = emit, _Stdin()
    results: list[str] = []
    try:
        threads = [
            threading.Thread(
                target=lambda: results.append(sidecar._request_native_tool("ping", {}))
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sidecar._emit, sidecar.sys.stdin = original_emit, original_stdin
    assert state["max_active"] == 1, state
    assert len(results) == 2 and all(json.loads(result)["ok"] for result in results)


def main() -> None:
    _check_native_transport_serialized()
    set_speak_surface("home")
    home = _names("home")
    assert "terminal" in home, home
    assert "shell_run" not in home
    assert "project_run" not in home
    assert "write_file" in home
    assert "project_write_file" not in home
    assert "read_file" in home
    assert "search_files" in home
    assert "web_search" in home
    assert "web_extract" in home
    assert "process_manage" in home
    assert "apply_patch" in home
    assert "patch" not in home  # alias only — no dual schema
    assert "settings_get" in home

    set_speak_surface("ide_companion")
    ide = _names("ide_companion")
    assert "terminal" in ide, ide
    assert "project_run" not in ide
    assert "shell_run" not in ide
    assert "write_file" in ide
    assert "project_write_file" not in ide
    assert "process_manage" in ide
    assert "apply_patch" in ide
    assert "patch" not in ide

    preload = sorted(
        _HERMES_CORE_LEFTOVERS
        | {"terminal", "write_file", "process_manage", "apply_patch", "skills_list"}
    )
    for surface in ("home", "ide_companion"):
        visible = _simulate_install(surface, preload)
        leftover = visible & _HERMES_CORE_LEFTOVERS
        assert not leftover, (surface, leftover)
        assert "terminal" in visible
        assert "write_file" in visible
        assert "process_manage" in visible
        assert "apply_patch" in visible
        assert "patch" not in visible
        assert "skills_list" not in visible

    print(
        "absorbed_tool_wire ok",
        f"home_terminal={'terminal' in home}",
        f"ide_terminal={'terminal' in ide}",
        f"home_n={len(home)}",
        f"ide_n={len(ide)}",
    )


if __name__ == "__main__":
    main()
