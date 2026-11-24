"""Wire: model-visible schemas use Hermes-familiar Iris names; install drops CORE."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from iris.engine import _sidecar_main as sidecar
from iris.infrastructure.speak_capability import engine_tool_schemas, set_speak_surface

# Hermes CORE leftovers after Unit1 strip — must not survive Iris-only install.
_HERMES_CORE_LEFTOVERS = frozenset(
    {
        "process_manage",
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

    return SimpleNamespace(register=register, registered=registered)


def _simulate_install(surface: str, preload: list[str]) -> set[str]:
    """Call real _install_iris_engine_tools with a stub Hermes registry."""
    fake = _fake_registry()
    tools_mod = types.ModuleType("tools")
    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = fake
    tools_mod.registry = registry_mod
    prev_tools = sys.modules.get("tools")
    prev_reg = sys.modules.get("tools.registry")
    sys.modules["tools"] = tools_mod
    sys.modules["tools.registry"] = registry_mod
    agent = SimpleNamespace(
        tools=[
            {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in preload
        ],
        valid_tool_names=set(preload),
    )
    try:
        installed = sidecar._install_iris_engine_tools(agent, surface=surface)
    finally:
        if prev_tools is None:
            sys.modules.pop("tools", None)
        else:
            sys.modules["tools"] = prev_tools
        if prev_reg is None:
            sys.modules.pop("tools.registry", None)
        else:
            sys.modules["tools.registry"] = prev_reg
    visible = {
        str(row.get("function", {}).get("name") or "")
        for row in (agent.tools or [])
        if isinstance(row, dict)
    }
    assert visible == set(installed) == set(agent.valid_tool_names)
    assert visible == set(fake.registered)
    return visible


def main() -> None:
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
    assert "process_manage" not in home
    assert "settings_get" in home

    set_speak_surface("ide_companion")
    ide = _names("ide_companion")
    assert "terminal" in ide, ide
    assert "project_run" not in ide
    assert "shell_run" not in ide
    assert "write_file" in ide
    assert "project_write_file" not in ide
    assert "process_manage" not in ide

    preload = sorted(_HERMES_CORE_LEFTOVERS | {"terminal", "write_file", "skills_list"})
    for surface in ("home", "ide_companion"):
        visible = _simulate_install(surface, preload)
        leftover = visible & _HERMES_CORE_LEFTOVERS
        assert not leftover, (surface, leftover)
        assert "terminal" in visible
        assert "write_file" in visible
        assert "skills_list" not in visible
        assert "process_manage" not in visible

    print(
        "absorbed_tool_wire ok",
        f"home_terminal={'terminal' in home}",
        f"ide_terminal={'terminal' in ide}",
        f"home_n={len(home)}",
        f"ide_n={len(ide)}",
    )


if __name__ == "__main__":
    main()
