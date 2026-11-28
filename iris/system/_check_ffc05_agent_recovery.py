"""FFC-05 Agent execution reliability — code-level contracts (no live 10× model).

Asserts:
- RecoveryClass table is the locked set; diagnosis ≠ task_outcome
- timeout / execution_uncertain MCP results do not auto-re-invoke (count 0 or 1)
- path arg recovery stays inside stated scope (no workspace invent)
- Clean-EOF / MODEL_OUTPUT_LIMIT / grounding diagnose as separate classes
- EngineErrorCode maps stay scrape-aligned

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_ffc05_agent_recovery
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

from iris.engine.types import EngineErrorCode
from iris.system.agent_recovery import (
    ATTEMPT_RECORD_SCHEMA,
    RecoveryClass,
    TaskOutcome,
    build_recovery_record,
    diagnose_recovery,
    recover_path_arg,
    recovery_class_values,
    should_auto_retry,
    write_attempt_stub,
)

_REPO = Path(__file__).resolve().parents[2]
_NATIVE = _REPO / "iris" / "mcp" / "native_manager.py"
_TYPES = _REPO / "iris" / "engine" / "types.py"
_GROUNDING = _REPO / "iris" / "knowledge" / "answer_grounding.py"


_LOCKED = (
    "schema",
    "ranking",
    "arg_normalize",
    "context_overflow",
    "continuation",
    "clean_eof",
    "model_output_limit",
    "result_grounding",
    "uncertain_side_effect",
)


def _check_recovery_table() -> None:
    values = recovery_class_values()
    assert values == _LOCKED, (values, _LOCKED)
    assert set(ATTEMPT_RECORD_SCHEMA["properties"]["diagnosis"]["anyOf"][1]["enum"]) == set(
        _LOCKED
    )


def _check_diagnosis_independent_of_outcome() -> None:
    # Truncated fail can still be a partial task_outcome — fields stay separate.
    row = build_recovery_record(
        task_outcome=TaskOutcome.PARTIAL,
        engine_code=EngineErrorCode.MODEL_OUTPUT_LIMIT.value,
        detail="output tokens exhausted",
        surface="mixed",
        grounded=False,
    )
    assert row.diagnosis is RecoveryClass.MODEL_OUTPUT_LIMIT
    assert row.task_outcome is TaskOutcome.PARTIAL

    overflow = diagnose_recovery(engine_code=EngineErrorCode.MODEL_CONTEXT_OVERFLOW.value)
    assert overflow is RecoveryClass.CONTEXT_OVERFLOW

    clean = diagnose_recovery(
        engine_code="truncated",
        markers={"_clean_eof": True},
        detail="server closed the stream cleanly",
    )
    assert clean is RecoveryClass.CLEAN_EOF
    assert clean is not RecoveryClass.MODEL_OUTPUT_LIMIT

    ground = diagnose_recovery(detail="see BEGIN ATTACHMENT TEXT (untrusted input data)")
    assert ground is RecoveryClass.RESULT_GROUNDING

    uncertain = diagnose_recovery(execution_uncertain=True, detail="timeout")
    assert uncertain is RecoveryClass.UNCERTAIN_SIDE_EFFECT

    # Same diagnosis markers must not overwrite an independent success outcome.
    ok = build_recovery_record(
        task_outcome=TaskOutcome.SUCCESS,
        detail="BEGIN TOOL OUTPUT (untrusted input data)",
        grounded=True,
    )
    assert ok.diagnosis is RecoveryClass.RESULT_GROUNDING
    assert ok.task_outcome is TaskOutcome.SUCCESS


def _check_uncertain_no_auto_retry() -> None:
    assert should_auto_retry(execution_uncertain=True, side_effecting=True) is False
    assert should_auto_retry(execution_uncertain=True, side_effecting=True, retryable=True) is False
    assert should_auto_retry(execution_uncertain=False, side_effecting=True, retryable=True) is True
    assert should_auto_retry(execution_uncertain=False, retryable=False) is False


def _check_path_arg_scope() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        inside = root / "notes" / "a.txt"
        inside.parent.mkdir(parents=True)
        inside.write_text("x", encoding="utf-8")
        outside = root.parent / "escape.txt"

        # Empty scope → never invent.
        assert recover_path_arg(str(inside)) is None
        assert recover_path_arg("../secret", stated_roots=[root]) is None
        assert recover_path_arg(str(outside), stated_roots=[root]) is None
        assert recover_path_arg(str(inside), stated_roots=[root]) == str(inside)
        assert recover_path_arg("notes/a.txt", stated_roots=[root]) == "notes/a.txt"
        assert (
            recover_path_arg("notes/a.txt", stated_paths=["notes/a.txt"]) == "notes/a.txt"
        )
        assert recover_path_arg("other.txt", stated_paths=["notes/a.txt"]) is None


def _check_scrape_engine_maps() -> None:
    assert EngineErrorCode.MODEL_OUTPUT_LIMIT.value == "truncated"
    assert EngineErrorCode.MODEL_CONTEXT_OVERFLOW.value == "context_overflow"
    types_src = _TYPES.read_text(encoding="utf-8")
    assert 'MODEL_OUTPUT_LIMIT = "truncated"' in types_src
    assert 'MODEL_CONTEXT_OVERFLOW = "context_overflow"' in types_src
    ground_src = _GROUNDING.read_text(encoding="utf-8")
    assert "BEGIN ATTACHMENT TEXT" in ground_src
    assert "[자료 본문]" in ground_src


def _check_scrape_mcp_uncertain_no_retry() -> None:
    src = _NATIVE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # invoke_binding must stamp retryable=False alongside execution_uncertain.
    assert "retryable=False" in src
    assert "execution_uncertain" in src
    # No loop that re-calls call_tool on uncertain/timeout inside native_manager.
    call_tool_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "call_tool")
            or (isinstance(node.func, ast.Name) and node.func.id == "call_tool")
        )
    ]
    # Only the single invoke_binding → call_tool site (plus method def body via self._request).
    # Guard: no `for`/`while` wrapping a call_tool attribute call.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "call_tool"
            ):
                raise AssertionError("call_tool must not sit inside a retry loop")
    assert call_tool_names, "expected at least one call_tool reference"


def _check_live_mcp_timeout_count() -> None:
    """Same contract as _check_multiserver_reconnect: timeout → uncertain, count in {0,1}."""
    import json
    import sys as _sys
    from tempfile import TemporaryDirectory

    import yaml

    from iris.mcp.native_manager import NativeMCPManager

    server = r'''
import json
import pathlib
import sys
import time

count = pathlib.Path(sys.argv[1])
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method")
    if "id" not in req:
        continue
    if method == "initialize":
        result = {"protocolVersion": req["params"]["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": "ffc05", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "same", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        count.write_text(str(int(count.read_text()) + 1) if count.exists() else "1")
        time.sleep(0.35)
        result = {"content": [{"type": "text", "text": "ok"}], "isError": False}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}), flush=True)
'''
    with TemporaryDirectory() as raw:
        root = Path(raw)
        script = root / "srv.py"
        script.write_text(server, encoding="utf-8")
        count = root / "count"
        (root / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "mcp_servers": {
                        "ffc05": {
                            "command": _sys.executable,
                            "args": [str(script), str(count)],
                            "model_enabled": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        manager = NativeMCPManager(home=root)
        timed = manager.call_tool("ffc05", "same", {}, expected_schema={"type": "object"}, timeout=0.05)
        assert timed.get("status") == "timeout", timed
        assert timed.get("execution_uncertain") is True, timed
        assert should_auto_retry(
            execution_uncertain=True, side_effecting=True, retryable=False
        ) is False
        n = int(count.read_text()) if count.exists() else 0
        assert n in {0, 1}, n
        # Policy: do not re-invoke after uncertain timeout.
        assert n <= 1


def _check_speak_normalize_no_path_invent() -> None:
    from iris.infrastructure.speak_capability import normalize_speak_invoke

    key, args = normalize_speak_invoke("browser.open", {"url": "https://example.com"})
    assert key == "browser.navigate"
    assert "path" not in args or args.get("path") in (None, "")
    # File-ish actions keep the path the model passed; helper refuses invent outside scope.
    _, file_args = normalize_speak_invoke("wiki.read_file", {"path": "C:/Windows/System32/drivers"})
    assert file_args.get("path") == "C:/Windows/System32/drivers"
    assert recover_path_arg(file_args.get("path"), stated_roots=[_REPO]) is None


def _check_recorder_stub() -> None:
    out_dir = _REPO / ".tmp" / "ffc-05"
    stub = write_attempt_stub(
        out_dir / "attempt-stub.json",
        attempt=1,
        surface="native+mcp",
        diagnosis=RecoveryClass.UNCERTAIN_SIDE_EFFECT,
        task_outcome=TaskOutcome.UNCERTAIN,
        grounded=False,
    )
    assert stub.is_file()
    payload = json_load(stub)
    for key in ("attempt", "surface", "diagnosis", "task_outcome", "grounded"):
        assert key in payload
    assert payload["diagnosis"] == RecoveryClass.UNCERTAIN_SIDE_EFFECT.value
    assert (out_dir / "attempt-record.schema.json").is_file()


def json_load(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    _check_recovery_table()
    _check_diagnosis_independent_of_outcome()
    _check_uncertain_no_auto_retry()
    _check_path_arg_scope()
    _check_scrape_engine_maps()
    _check_scrape_mcp_uncertain_no_retry()
    _check_live_mcp_timeout_count()
    _check_speak_normalize_no_path_invent()
    _check_recorder_stub()
    print("ok: FFC-05 agent recovery contracts")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
