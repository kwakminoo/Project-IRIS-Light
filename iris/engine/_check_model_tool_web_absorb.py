"""Unit — web_search/web_extract absorbed into Iris Control (REPLACE).

Sidecar disables Hermes web; MODEL_TOOL_NAMES owns Iris short names → web.run_*.
Speak must not invent web schemas; product path must not import tools.web_tools.
browser ≠ web: absorb asserts require web only (not browser).
"""

from __future__ import annotations

import ast
from pathlib import Path

from iris.engine.model_tool_names import (
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
_IRIS_WEB = Path(__file__).resolve().parents[1] / "system" / "iris_web.py"
_CONTROL_WEB = Path(__file__).resolve().parents[1] / "ui" / "control_actions" / "web.py"

# Hermes web toolset aliases that MUST appear in product disabled_toolsets.
# browser is a separate page-driving toolset — do not require it here.
_WEB_DISABLE_ALIASES = frozenset({"web", "web_tools"})

_NON_OVERLAP_ENGINE = frozenset(
    {
        "wiki_search",
        "diagram_render",
        "app_open",
        "ide_open_folder",
        "calendar_list_events",
    }
)


def check_iris_absorb_flags() -> None:
    assert upstream_keep_names() == ()
    for name in ("web_search", "web_extract"):
        row = lookup(name)
        assert row is not None
        assert row["keep_upstream"] is False
        assert row["toolset"] == "web"
        assert row["owner"] == "iris"
        assert name in iris_backed_model_names()
        schema = openai_schema(name)
        assert "description" in schema and "parameters" in schema
    for surface in ("home", "ide"):
        regs = {row[0]: row[1] for row in iris_model_registrations(surface)}
        assert regs.get("web_search") == "web.run_search"
        assert regs.get("web_extract") == "web.run_extract"
    hidden = names_hidden_from_model()
    assert "web_run_search" in hidden
    assert "web_run_extract" in hidden
    print("iris_absorb_flags ok", f"iris_web={('web_search', 'web_extract')}")


def check_sidecar_disables_web() -> None:
    src = _SIDECAR.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(_SIDECAR))
    literals = _disabled_toolsets_literals(tree)
    assert literals, "sidecar must pass disabled_toolsets to AIAgent"
    flat = {name for row in literals for name in row}
    assert flat & {"file", "file_tools"}, f"missing file: {literals}"
    assert flat & {"terminal", "terminal_tools"}, f"missing terminal: {literals}"
    assert flat & _WEB_DISABLE_ALIASES, f"product path must disable web: {literals}"
    # Absorb check does not force-disable browser (page driving ≠ search/extract).
    print("sidecar_disables_web ok", f"disabled_toolsets={literals[0]}")


def check_non_overlap_speak_schemas() -> None:
    schema_names = {str(row["name"]) for row in engine_tool_schemas()}
    missing = _NON_OVERLAP_ENGINE - schema_names
    assert not missing, (
        f"familiar fold stripped non-overlap Speak tools: {sorted(missing)}"
    )
    for name in ("shell_run", "local_write_file", "project_write_file", "control_invoke"):
        assert name not in schema_names, f"overlap still exposed: {name}"
    for name in ("web_run_search", "web_run_extract"):
        assert name not in schema_names, f"Speak twin must stay hidden: {name}"
    # Short names are model tools, not Speak invents.
    for name in ("web_search", "web_extract"):
        assert name not in schema_names, (
            f"do not invent Speak schema for Iris model web tool: {name}"
        )
    print(
        "non_overlap_speak_schemas ok",
        f"kept={sorted(_NON_OVERLAP_ENGINE)}",
        f"schemas={len(schema_names)}",
    )


def check_no_agent_web_tools_import() -> None:
    import re

    # Import of Hermes checkout web tools package is forbidden on product path.
    forbidden_import = re.compile(r"(?m)^\s*(from|import)\s+tools(?:\.|\s|$)")
    # Call sites use name + "("; avoid putting that literal in target modules.
    hermes_fn = "web_" + "search_tool("
    hermes_fn_ex = "web_" + "extract_tool("
    for path in (_IRIS_WEB, _CONTROL_WEB):
        text = path.read_text(encoding="utf-8")
        assert not forbidden_import.search(text), f"{path.name} imports tools package"
        assert hermes_fn not in text, f"{path.name} calls Hermes search tool"
        assert hermes_fn_ex not in text, f"{path.name} calls Hermes extract tool"
    print("no_agent_web_tools_import ok")


def main() -> None:
    check_iris_absorb_flags()
    check_sidecar_disables_web()
    check_non_overlap_speak_schemas()
    check_no_agent_web_tools_import()


if __name__ == "__main__":
    main()
