"""U02 / W11-E — Unified Tool Contract over SpeakAllowlist / SpeakTools (SSOT).

Fails when:
- bare grants emit additionalProperties:true (open default)
- no-arg / bare grants lack empty-object schema
- dangerous / arg-required tools still emit EMPTY schema
- empty schema actions are not pinned on EMPTY_SCHEMA_ACTIONS
- ide_companion terminal schema lacks command/file (parity with handlers)
- IrisToolContract defaults are optimistic (parallel_safe / headless)
- ToolResult from Control path omits status / error_code / duration_ms
- duplicate model-facing names in engine_tool_schemas

Run:
  .venv\\Scripts\\python.exe -m iris.infrastructure._check_tool_contract
"""

from __future__ import annotations

import json
import time

from iris.infrastructure.absorbed_tool_aliases import action_to_model_name, resolve_action
from iris.infrastructure.speak_capability import (
    EMPTY_OBJECT_SCHEMA,
    EMPTY_SCHEMA_ACTIONS,
    PHASE4_ALLOWLIST,
    SpeakGrant,
    SpeakTools,
    ToolResult,
    engine_tool_name,
    engine_tool_schemas,
    grants_for_surface,
    iris_tool_contract_from_grant,
    normalize_speak_invoke,
    resolve_legacy_name,
    validate_tool_arguments,
)

# High-risk / arg-required tools that must never stay EMPTY.
_MUST_NONEMPTY_ACTIONS = frozenset(
    {
        "project.run",
        "shell.run",
        "project.write_file",
        "process.manage",
        "project.apply_patch",
        "browser.navigate",
        "browser.click",
        "browser.type",
        "browser.search",
        "browser.media",
        "browser.mini_player",
        "browser.scroll",
        "wiki.write_user_note",
        "email.send",
        "project.delete",
        "project.rename_file",
    }
)


def _schema_chars(surface: str) -> int:
    return len(json.dumps(engine_tool_schemas(surface), ensure_ascii=False, separators=(",", ":")))


def _is_empty_schema(params: dict) -> bool:
    return (
        params.get("type") == "object"
        and params.get("properties") == {}
        and params.get("additionalProperties") is False
        and not params.get("required")
        and not params.get("anyOf")
    )


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

    explicit = 0
    empty_emitted = 0
    for grant in PHASE4_ALLOWLIST.grants:
        if grant.parameters is None or _is_empty_schema(dict(grant.parameters)):
            empty_emitted += 1
            assert grant.action in EMPTY_SCHEMA_ACTIONS, (
                f"empty/bare grant not on EMPTY_SCHEMA_ACTIONS: {grant.action}"
            )
        else:
            explicit += 1

    for action in _MUST_NONEMPTY_ACTIONS:
        grant = PHASE4_ALLOWLIST.grant(action)
        assert grant is not None, action
        assert grant.parameters is not None and not _is_empty_schema(dict(grant.parameters)), (
            f"dangerous tool still EMPTY: {action}"
        )

    for name in EMPTY_SCHEMA_ACTIONS:
        assert PHASE4_ALLOWLIST.grant(name) is not None, f"allowlist ghost: {name}"

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

    # ide terminal must not be EMPTY — parity with handlers (command|file).
    ide_by = {str(s["name"]): s for s in ide}
    term = ide_by["terminal"]["parameters"]
    assert not _is_empty_schema(term), "ide terminal must not emit EMPTY_OBJECT_SCHEMA"
    props = term.get("properties") or {}
    assert "command" in props, term
    assert "file" in props or "rel_path" in props, term

    home_term = {str(s["name"]): s for s in home}["terminal"]["parameters"]
    assert "command" in (home_term.get("properties") or {}), home_term

    # validate_tool_arguments
    validate_tool_arguments(None, {"q": 1})  # undeclared API still permissive
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

    run_grant = PHASE4_ALLOWLIST.grant("project.run")
    assert run_grant is not None and run_grant.parameters is not None
    validate_tool_arguments(run_grant.parameters, {"command": "python -V"})
    validate_tool_arguments(run_grant.parameters, {"file": "main.py"})
    try:
        validate_tool_arguments(run_grant.parameters, {})
    except ValueError:
        pass
    else:
        raise AssertionError("project.run must require command or file")

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

    # Contract helper + legacy seed map — conservative defaults
    assert resolve_legacy_name("iris.wiki.list_notes") == "wiki.list_notes"
    g = PHASE4_ALLOWLIST.grant("wiki.list_notes")
    assert g is not None
    contract = iris_tool_contract_from_grant(g)
    assert contract.canonical_name == "wiki.list_notes"
    assert contract.control_action == "wiki.list_notes"
    assert contract.input_schema == EMPTY_OBJECT_SCHEMA or _is_empty_schema(
        dict(contract.input_schema)
    )
    assert "iris.wiki.list_notes" in contract.aliases
    assert isinstance(contract.profiles, frozenset)
    assert contract.parallel_safe is False
    assert contract.headless_supported is True  # PURE + not confirm-heavy

    surface_g = PHASE4_ALLOWLIST.grant("project.run")
    assert surface_g is not None
    surface_c = iris_tool_contract_from_grant(surface_g)
    assert surface_c.parallel_safe is False
    assert surface_c.headless_supported is False

    # SpeakTools.invoke validates declared schemas (bare → EMPTY)
    seen: list[tuple[str, dict]] = []

    class _Surf:
        def invoke(self, action: str, args: dict) -> dict | None:
            time.sleep(0.001)
            seen.append((action, dict(args)))
            if action == "project.run":
                return {
                    "ok": True,
                    "action": action,
                    "status": "success",
                    "result": dict(args),
                    "error": None,
                    "call_id": "ctl-1",
                }
            if action == "wiki.list_notes":
                return {
                    "ok": False,
                    "action": action,
                    "status": "failed",
                    "result": {},
                    "error": "boom",
                }
            return {"ok": True, "action": action, "status": "success", "result": dict(args), "error": None}

    tools = SpeakTools(
        PHASE4_ALLOWLIST,
        surface=_Surf(),
        pure_handlers={
            "ping": lambda _a: ToolResult(ok=True, action="ping", data={"pong": True}),
            "wiki.list_notes": lambda _a: ToolResult(
                ok=True, action="wiki.list_notes", data={"notes": []}
            ),
        },
    )
    bad = tools.invoke("local.read_file", {})
    assert bad.ok is False
    assert bad.error_code == "invalid_arguments"
    ok_ping = tools.invoke("iris.tools.ping", {})
    assert ok_ping.ok is True

    # Bare zero-arg grant rejects unexpected keys (EMPTY semantics).
    bare_reject = tools.invoke("wiki.list_notes", {"unexpected": 1})
    assert bare_reject.ok is False
    assert bare_reject.error_code == "invalid_arguments"

    # Control path wires status / error_code / duration_ms / call_id when present.
    run_ok = tools.invoke("project.run", {"command": "echo hi"})
    assert run_ok.ok is True
    assert run_ok.status == "success"
    assert run_ok.call_id == "ctl-1"
    assert run_ok.duration_ms is not None and run_ok.duration_ms >= 0
    assert run_ok.tool_name == "terminal"

    # Model alias: cmd/shell → command before validate (Final Gate shell.run miss).
    cmd_n, cmd_args = normalize_speak_invoke("shell.run", {"cmd": "echo x"})
    assert cmd_n == "shell.run"
    assert cmd_args == {"command": "echo x"}
    shell_n, shell_args = normalize_speak_invoke("shell.run", {"shell": "echo y"})
    assert shell_n == "shell.run" and shell_args == {"command": "echo y"}
    keep_n, keep_args = normalize_speak_invoke(
        "shell.run", {"command": "keep", "cmd": "drop"}
    )
    assert keep_n == "shell.run" and keep_args == {"command": "keep"}
    seen.clear()
    cmd_ok = tools.invoke("shell.run", {"cmd": "echo x"})
    assert cmd_ok.ok is True, cmd_ok
    assert cmd_ok.error_code is None
    assert seen and seen[-1][0] == "shell.run"
    assert seen[-1][1] == {"command": "echo x"}
    assert "cmd" not in seen[-1][1]

    # Model alias: browser.open+url → browser.navigate (open grant has empty schema).
    open_n, open_args = normalize_speak_invoke(
        "browser.open", {"url": "https://example.com"}
    )
    assert open_n == "browser.navigate"
    assert open_args.get("url") == "https://example.com"
    bare_open_n, bare_open_args = normalize_speak_invoke("browser.open", {})
    assert bare_open_n == "browser.open" and bare_open_args == {}
    seen.clear()
    nav_ok = tools.invoke("browser.open", {"url": "https://example.com"})
    assert nav_ok.ok is True, nav_ok
    assert nav_ok.action == "browser.navigate"
    assert seen and seen[-1][0] == "browser.navigate"
    assert seen[-1][1].get("url") == "https://example.com"

    home_chars = _schema_chars("home")
    ide_chars = _schema_chars("ide_companion")
    print("tool_contract ok")
    print(f"  engine_schema_home_count={len(home)}")
    print(f"  engine_schema_ide_count={len(ide)}")
    print(f"  engine_schema_home_chars={home_chars}")
    print(f"  engine_schema_ide_chars={ide_chars}")
    print(f"  grants_explicit={explicit}")
    print(f"  grants_empty={empty_emitted}")
    print(f"  empty_allowlist={len(EMPTY_SCHEMA_ACTIONS)}")


if __name__ == "__main__":
    main()
