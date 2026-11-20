"""Unit — execute_code absorbed into Iris Control (REPLACE).

Sidecar disables Hermes code_execution (+ remaining Hermes chat toolsets);
MODEL_TOOL_NAMES owns Iris short name → chat.exec_python.
"""

from __future__ import annotations

import ast
from pathlib import Path

from iris.engine.model_tool_names import (
    adapt_control_invoke,
    iris_backed_model_names,
    iris_model_registrations,
    lookup,
    names_hidden_from_model,
    openai_schema,
    upstream_keep_names,
)
from iris.engine._check_sidecar_disables_agent_file_terminal import (
    _disabled_toolsets_literals,
)
from iris.infrastructure.tool_capability import engine_tool_schemas

_SIDECAR = Path(__file__).resolve().with_name("_sidecar_main.py")

# Hermes toolsets that product chat must not expose (sidecar + config sync).
_REQUIRED_DISABLED = frozenset(
    {
        "file",
        "terminal",
        "web",
        "code_execution",
        "memory",
        "delegation",
        "clarify",
        "browser",
        "browser-use",
        "browser-cdp",
        "computer_use",
        "tts",
        "vision",
    }
)


def check_iris_absorb_flags() -> None:
    assert upstream_keep_names() == ()
    row = lookup("execute_code")
    assert row is not None
    assert row["keep_upstream"] is False
    assert row["toolset"] == "code"
    assert row["owner"] == "iris"
    assert "execute_code" in iris_backed_model_names()
    schema = openai_schema("execute_code")
    assert "description" in schema and "parameters" in schema
    props = schema["parameters"].get("properties") or {}
    assert "code" in props
    required = schema["parameters"].get("required") or []
    assert "code" in required
    for surface in ("home", "ide"):
        regs = {r[0]: r[1] for r in iris_model_registrations(surface)}
        assert regs.get("execute_code") == "chat.exec_python"
    hidden = names_hidden_from_model()
    assert "chat_exec_python" in hidden
    print("iris_absorb_flags ok", "execute_code→chat.exec_python")


def check_absorbed_never_keep_upstream() -> None:
    """Product chat path: absorbed Iris tools must not reintroduce Hermes keep_upstream."""
    assert upstream_keep_names() == (), upstream_keep_names()
    for name in iris_backed_model_names():
        row = lookup(name)
        assert row is not None, name
        assert row["owner"] == "iris", name
        assert row["keep_upstream"] is False, (
            f"{name} keep_upstream must stay False after absorb"
        )
    code = lookup("execute_code")
    assert code is not None and code["keep_upstream"] is False
    # Sidecar must not re-enable Hermes-native code_execution toolset.
    src = _SIDECAR.read_text(encoding="utf-8")
    assert "code_execution" in src
    flat = {n for row in _disabled_toolsets_literals(ast.parse(src)) for n in row}
    assert "code_execution" in flat, flat
    print("absorbed_never_keep_upstream ok")


def check_adapt_maps_code() -> None:
    action, args = adapt_control_invoke(
        "execute_code", "home", {"code": "print(1)", "timeout": 5}
    )
    assert action == "chat.exec_python"
    assert args["code"] == "print(1)"
    assert args.get("timeout_s") == 5

    action, args = adapt_control_invoke(
        "execute_code", "ide", {"source": "x=1", "timeout_s": 10}
    )
    assert action == "chat.exec_python"
    assert args == {"code": "x=1", "timeout_s": 10}
    print("adapt_maps_code ok")


def check_sidecar_disables_code_and_rest() -> None:
    src = _SIDECAR.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(_SIDECAR))
    literals = _disabled_toolsets_literals(tree)
    assert literals, "sidecar must pass disabled_toolsets to AIAgent"
    flat = {name for row in literals for name in row}
    missing = sorted(_REQUIRED_DISABLED - flat)
    assert not missing, f"sidecar disabled_toolsets missing {missing}: {literals}"
    assert "execute_code" in iris_backed_model_names()
    print("sidecar_disables_code_and_rest ok", f"disabled_toolsets={literals[0]}")


def check_non_overlap_speak_schemas() -> None:
    schema_names = {str(row["name"]) for row in engine_tool_schemas()}
    assert "chat_exec_python" not in schema_names, (
        "Speak twin must stay hidden: chat_exec_python"
    )
    assert "execute_code" not in schema_names, (
        "do not invent Speak schema for Iris model code tool: execute_code"
    )
    print("non_overlap_speak_schemas ok")


def main() -> None:
    check_iris_absorb_flags()
    check_absorbed_never_keep_upstream()
    check_adapt_maps_code()
    check_sidecar_disables_code_and_rest()
    check_non_overlap_speak_schemas()


if __name__ == "__main__":
    main()
