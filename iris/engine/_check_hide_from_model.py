"""Unit 3 — model_names active → hide overlapping Speak names off the model.

Grants stay on PHASE4; engine_tool_schemas / Speak catalog omit the hide set.
Model names remain installed by sidecar (Unit 1).
"""

from __future__ import annotations

from iris.engine.model_tool_names import (
    catalog_uses_model_tool_names,
    iris_backed_model_names,
    actions_hidden_from_model,
    names_hidden_from_model,
)
from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    default_agent_tools,
    engine_tool_schemas,
    engine_names_hidden_from_model,
)


_REQUIRED_HIDE = frozenset(
    {
        "project_write_file",
        "project_read_file",
        "project_list_files",
        "project_run",
        "shell_run",
        "local_write_file",
        "local_read_file",
        "local_search_files",
        "control_invoke",
    }
)


def check_hide_table() -> None:
    hidden = names_hidden_from_model()
    assert _REQUIRED_HIDE <= frozenset(hidden), (
        f"hide table missing {_REQUIRED_HIDE - frozenset(hidden)}"
    )
    actions = actions_hidden_from_model()
    assert "project.write_file" in actions
    assert "control.invoke" in actions
    assert "local.write_file" in actions
    print("hide_table ok", f"n={len(hidden)}")


def check_grants_kept() -> None:
    names = set(PHASE4_ALLOWLIST.names())
    for action in actions_hidden_from_model():
        assert action in names, f"PHASE4 lost grant for hidden action: {action}"
    assert "control.invoke" in names
    assert "shell.run" in names
    assert "project.write_file" in names
    print("grants_kept ok")


def check_model_schemas_hidden() -> None:
    assert catalog_uses_model_tool_names(), (
        "model_tool_names catalog must be active for hide_from_model"
    )
    model_hidden = engine_names_hidden_from_model()
    assert _REQUIRED_HIDE <= model_hidden, (
        f"model hide inactive or incomplete: {_REQUIRED_HIDE - model_hidden}"
    )
    schema_names = {str(row["name"]) for row in engine_tool_schemas()}
    for name in _REQUIRED_HIDE:
        assert name not in schema_names, f"overlap still on model schema: {name}"
    catalog_names = {row.name for row in default_agent_tools().catalog()}
    for action in actions_hidden_from_model():
        assert action not in catalog_names, f"overlap still on model catalog: {action}"
    # Model OpenAI names are not Speak grants; sidecar installs them separately.
    for model_name in iris_backed_model_names():
        assert model_name not in schema_names
    # Overlap Speak twins are absent from model schemas when model_names are active.
    for name in ("project_run", "local_read_file", "local_search_files"):
        assert name not in schema_names, f"overlap still on model schema: {name}"
    # Non-overlap Speak tools remain.
    assert "wiki_list_notes" in schema_names or "get_state" in schema_names
    print(
        "model_schemas_hidden ok",
        f"schemas={len(schema_names)}",
        f"hidden={len(model_hidden)}",
    )


def check_invoke_still_allowed() -> None:
    """Hide is exposure-only; SpeakTools.invoke still accepts the grant."""
    tools = default_agent_tools()
    # Headless UI surface → requires_iris_ui, not not_allowed.
    out = tools.invoke("project.write_file", {"rel_path": "a.py", "content": "x"})
    assert out.error != "not_allowed: project.write_file", out
    ctrl = tools.invoke("control.invoke", {"action": "ping", "args": {}})
    assert "not_allowed: control.invoke" not in (ctrl.error or ""), ctrl
    print("invoke_still_allowed ok")


def main() -> None:
    check_hide_table()
    check_grants_kept()
    check_model_schemas_hidden()
    check_invoke_still_allowed()


if __name__ == "__main__":
    main()
