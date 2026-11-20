"""Unit — agent surface inventory lever (speak vs control vs skills).

Fails when speak tools regress to the MCP triple, control.invoke is missing,
or teaching / skills still name iris_get_state / iris_get_catalog / iris_invoke.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_surface_inventory
"""

from __future__ import annotations

from iris.system.agent_surface_inventory import (
    build_inventory,
    format_summary,
)

_MCP_TRIPLE = ("iris_get_state", "iris_get_catalog", "iris_invoke")


def _main() -> None:
    inv = build_inventory()

    assert tuple(inv.speak_tools) != _MCP_TRIPLE, (
        "speak tools must not equal the MCP iris-control triple"
    )
    assert "control.invoke" in inv.speak_tools, (
        "control.invoke missing from speak tools: "
        f"{inv.speak_tools!r}"
    )
    for bad in _MCP_TRIPLE:
        assert bad not in inv.speak_tools, f"speak tools still list {bad}"

    assert inv.forbidden_mcp_triple_in_teaching is False, (
        "teaching/skills still contain iris_get_state / iris_get_catalog / "
        "iris_invoke as tool names"
    )

    assert inv.skill_names, "skill_names empty"
    assert inv.control_action_count > 0, "control_action_count is 0 (scan failed?)"
    root_posix = inv.skills_root.replace("\\", "/")
    assert root_posix.endswith("integrations/iris-skills") or (
        "/integrations/iris-skills" in root_posix
    ), f"skills_root must be integrations/iris-skills, got {inv.skills_root!r}"

    print("agent_surface_inventory ok")
    print(format_summary(inv))


if __name__ == "__main__":
    _main()
