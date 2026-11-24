"""U02 — Unified Tool Contract over SpeakAllowlist / SpeakTools (SSOT).

Fails when:
- bare grants emit additionalProperties:true (open default)
- no-arg / bare grants lack empty-object schema
- duplicate model-facing names in engine_tool_schemas
- ToolResult.as_dict omits structured optional fields when set

Run:
  .venv\\Scripts\\python.exe -m iris.infrastructure._check_tool_contract
"""

from __future__ import annotations

import json

from iris.infrastructure.absorbed_tool_aliases import action_to_model_name, resolve_action
from iris.infrastructure.speak_capability import (
    EMPTY_OBJECT_SCHEMA,
    PHASE4_ALLOWLIST,
    SpeakGrant,
    SpeakTools,
    ToolResult,
    engine_tool_name,
    engine_tool_schemas,
    grants_for_surface,
    iris_tool_contract_from_grant,
    resolve_legacy_name,
    validate_tool_arguments,
)


def _schema_chars(surface: str) -> int:
    return len(json.dumps(engine_tool_schemas(surface), ensure_ascii=False, separators=(",", ":")))


def _emitted_grants(surface: str) -> dict[str, SpeakGrant]:
    """Same ordering / terminal collapse as engine_tool_schemas."""
    terminal_action = resolve_action("terminal", surface)
    ordered: dict[str, SpeakGrant] = {}
    for grant in grants_for_surface(PHASE4_ALLOWLIST, surface):
        if action_to_model_name(grant.action) == "terminal":
            if grant.action != terminal_action:
                continue
        name = engine_tool_name(grant.action)
        if name in ordered:
            continue
        ordered[name] = grant
    return ordered


def main() -> None:
    home = engine_tool_schemas("home")
    ide = engine_tool_schemas("ide_companion")

    home_names = [str(s["name"]) for s in home]
    assert len(home_names) == len(set(home_names)), home_names
    ide_names = [str(s["name"]) for s in ide]
    assert len(ide_names) == len(set(ide_names)), ide_names

    by_model = _emitted_grants("home")
    assert set(by_model) == set(home_names)

    for schema in home:
        name = str(schema["name"])
        params = schema["parameters"]
        grant = by_model[name]
        if grant.parameters is None:
            assert params.get("type") == "object", (name, params)
            assert params.get("properties") == {}, (name, params)
            assert params.get("additionalProperties") is False, (
                name,
                "bare grant must use empty-object schema, not open additionalProperties",
                params,
            )
        else:
            assert params == dict(grant.parameters), (name, params, grant.parameters)
            if params.get("additionalProperties") is True:
                assert grant.parameters.get("additionalProperties") is True, name

    # No default open-object leak: every additionalProperties:true must be explicit on grant.
    for schema in home:
        params = schema["parameters"]
        if params.get("additionalProperties") is True:
            grant = by_model[str(schema["name"])]
            assert grant.parameters is not None, schema["name"]
            assert grant.parameters.get("additionalProperties") is True

    # validate_tool_arguments
    validate_tool_arguments(None, {"q": 1})
    validate_tool_arguments(EMPTY_OBJECT_SCHEMA, {})
    try:
        validate_tool_arguments(EMPTY_OBJECT_SCHEMA, {"x": 1})
    except ValueError:
        pass
    else:
        raise AssertionError("empty schema must reject extra keys")

    local_read = PHASE4_ALLOWLIST.grant("local.read_file")
    assert local_read is not None and local_read.parameters is not None
    validate_tool_arguments(local_read.parameters, {"path": "C:/a.txt"})
    try:
        validate_tool_arguments(local_read.parameters, {})
    except ValueError:
        pass
    else:
        raise AssertionError("required path missing must raise")

    # ToolResult structured fields in as_dict when set
    bare = ToolResult(ok=True, action="ping", data={}).as_dict()
    assert "call_id" not in bare
    assert "error_code" not in bare
    rich = ToolResult(
        ok=False,
        action="local.read_file",
        data={},
        error="missing required argument: path",
        call_id="c1",
        tool_name="local_read_file",
        status="error",
        error_code="invalid_arguments",
        error_message="missing required argument: path",
        retryable=False,
        duration_ms=12,
        truncated=False,
        artifact_ref="art://x",
    ).as_dict()
    for key in (
        "call_id",
        "tool_name",
        "status",
        "error_code",
        "error_message",
        "retryable",
        "duration_ms",
        "truncated",
        "artifact_ref",
    ):
        assert key in rich, key
    assert rich["call_id"] == "c1"
    assert rich["error_code"] == "invalid_arguments"
    assert rich["retryable"] is False

    # Contract helper + legacy seed map
    assert resolve_legacy_name("iris.wiki.list_notes") == "wiki.list_notes"
    g = PHASE4_ALLOWLIST.grant("wiki.list_notes")
    assert g is not None
    contract = iris_tool_contract_from_grant(g)
    assert contract.canonical_name == "wiki.list_notes"
    assert contract.control_action == "wiki.list_notes"
    assert contract.input_schema == EMPTY_OBJECT_SCHEMA
    assert "iris.wiki.list_notes" in contract.aliases
    assert isinstance(contract.profiles, frozenset)

    # SpeakTools.invoke validates declared schemas
    class _Surf:
        def invoke(self, action: str, args: dict) -> dict | None:
            return {"ok": True, "result": dict(args)}

    tools = SpeakTools(
        PHASE4_ALLOWLIST,
        surface=_Surf(),
        pure_handlers={
            "ping": lambda _a: ToolResult(ok=True, action="ping", data={"pong": True}),
        },
    )
    bad = tools.invoke("local.read_file", {})
    assert bad.ok is False
    assert bad.error_code == "invalid_arguments"
    ok_ping = tools.invoke("iris.tools.ping", {})
    assert ok_ping.ok is True

    home_chars = _schema_chars("home")
    ide_chars = _schema_chars("ide_companion")
    print("tool_contract ok")
    print(f"  engine_schema_home_count={len(home)}")
    print(f"  engine_schema_ide_count={len(ide)}")
    print(f"  engine_schema_home_chars={home_chars}")
    print(f"  engine_schema_ide_chars={ide_chars}")


if __name__ == "__main__":
    main()
