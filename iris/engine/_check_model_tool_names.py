"""Model tool name mapping contract + catalog wiring gate.

check_mapping_table: must pass when the registry is correct.
check_catalog_uses_table: FAIL until _sidecar_main file-location-loads/uses model_tool_names.
"""

from __future__ import annotations

from iris.engine.model_tool_names import (
    MODEL_TOOL_NAMES,
    IRIS_MODEL_TOOLSET,
    as_model_surface,
    catalog_uses_model_tool_names,
    control_action,
    iris_backed_model_names,
    iris_model_registrations,
    lookup,
    openai_schema,
    upstream_keep_names,
)


def check_mapping_table() -> None:
    assert iris_backed_model_names() == (
        "write_file",
        "read_file",
        "search_files",
        "terminal",
        "web_search",
        "web_extract",
        "execute_code",
    )
    assert upstream_keep_names() == ()

    assert control_action("write_file", "home") == "local.write_file"
    assert control_action("write_file", "ide") == "project.write_file"
    assert control_action("read_file", "home") == "local.read_file"
    assert control_action("read_file", "ide") == "project.read_file"
    assert control_action("search_files", "home") == "local.search_files"
    assert control_action("search_files", "ide") == "project.list_files"
    assert control_action("terminal", "home") == "shell.run"
    assert control_action("terminal", "ide") == "project.run"
    assert control_action("web_search", "home") == "web.run_search"
    assert control_action("web_search", "ide") == "web.run_search"
    assert control_action("web_extract", "home") == "web.run_extract"
    assert control_action("web_extract", "ide") == "web.run_extract"
    assert control_action("execute_code", "home") == "chat.exec_python"
    assert control_action("execute_code", "ide") == "chat.exec_python"

    for name in ("web_search", "web_extract"):
        row = lookup(name)
        assert row is not None
        assert row["keep_upstream"] is False
        assert row["toolset"] == "web"
        assert row["owner"] == "iris"

    code_row = lookup("execute_code")
    assert code_row is not None
    assert code_row["keep_upstream"] is False
    assert code_row["toolset"] == "code"
    assert code_row["owner"] == "iris"

    for name in iris_backed_model_names():
        row = MODEL_TOOL_NAMES[name]
        assert row["keep_upstream"] is False
        assert row["owner"] == "iris"
        schema = openai_schema(name)
        assert "description" in schema and "parameters" in schema

    assert as_model_surface("ide_companion") == "ide"
    assert as_model_surface("home") == "home"
    assert IRIS_MODEL_TOOLSET == "iris"

    regs = iris_model_registrations("home")
    assert [r[0] for r in regs] == list(iris_backed_model_names())
    assert regs[0][1] == "local.write_file"

    print("mapping_table ok", f"iris={iris_backed_model_names()}")


def check_catalog_uses_table() -> None:
    assert catalog_uses_model_tool_names(), (
        "FAIL catalog_uses_model_tool_names: "
        "_sidecar_main must _load_local_helper(\"model_tool_names\") (no package import)"
    )
    print("catalog_uses_model_tool_names ok")


def main() -> None:
    check_mapping_table()
    try:
        check_catalog_uses_table()
    except AssertionError as exc:
        print(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
