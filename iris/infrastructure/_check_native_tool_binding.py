"""Wave 1.3: trusted native binding snapshot and parent validation.

FIG-04 Wave-1: also asserts host TOOL_RESULT watch line shape (no trajectory).
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from iris.engine import runtime as runtime_mod
from iris.engine.runtime import Engine
from iris.engine.types import EngineHome, InternalSidecar
from iris.infrastructure.speak_capability import engine_tool_bindings, engine_tool_schemas

_TOOL_RESULT_RE = re.compile(
    r"^TOOL_RESULT request_id=\S+ tool_call_id=\S+ model_tool_name=\S+ "
    r"action=\S+ ok=(true|false) error_code=\S+(?: args=\S+)?$"
)


def main() -> None:
    home = {row.model_name: row for row in engine_tool_bindings("home")}
    ide = {row.model_name: row for row in engine_tool_bindings("ide_companion")}
    assert set(home) == {row["name"] for row in engine_tool_schemas("home")}
    assert set(ide) == {row["name"] for row in engine_tool_schemas("ide_companion")}
    assert all(len(row.fingerprint) == 64 for row in home.values())
    assert len({row.fingerprint for row in home.values()}) == len(home)
    assert home["terminal"].canonical_action == "shell.run"
    assert ide["terminal"].canonical_action == "project.run"
    assert home["terminal"].fingerprint != ide["terminal"].fingerprint
    assert home["process_manage"].fingerprint == ide["process_manage"].fingerprint

    absorbed = {
        "terminal",
        "process_manage",
        "write_file",
        "read_file",
        "search_files",
        "apply_patch",
        "web_search",
        "web_extract",
    }
    with tempfile.TemporaryDirectory() as tmp:
        for surface, bindings in (("home", home), ("ide_companion", ide)):
            engine = Engine(InternalSidecar(EngineHome(Path(tmp))))
            calls: list[tuple[str, dict]] = []
            watch_lines: list[str] = []
            engine.bind_tool_handler(
                lambda action, args: (
                    calls.append((action, dict(args))),
                    {"ok": True, "action": action},
                )[1]
            )

            def invoke(raw: dict) -> dict:
                writes: list[str] = []
                sink = SimpleNamespace(
                    stdin=SimpleNamespace(
                        write=lambda text: writes.append(text), flush=lambda: None
                    )
                )
                with patch.object(
                    runtime_mod, "_watch_trace", side_effect=watch_lines.append
                ):
                    engine._reply_to_tool_request(
                        sink,
                        raw,
                        surface=surface,
                        expected_turn_id="turn-1",
                        expected_session_id="session-1",
                        expected_workspace_id="workspace-1",
                    )
                return json.loads("".join(writes))["result"]

            for index, model_name in enumerate(sorted(absorbed)):
                binding = bindings[model_name]
                result = invoke(
                    {
                        "id": f"request-{index}",
                        "model_tool_name": binding.model_name,
                        "canonical_action": binding.canonical_action,
                        "schema_fingerprint": binding.fingerprint,
                        "turn_id": "turn-1",
                        "session_id": "session-1",
                        "workspace_id": "workspace-1",
                        "tool_call_id": f"call-{index}",
                        "args": {"probe": model_name},
                    }
                )
                assert result["ok"] is True, (surface, model_name, result)
            assert [action for action, _args in calls] == [
                bindings[name].canonical_action for name in sorted(absorbed)
            ]

            binding = bindings["process_manage"]
            base = {
                "id": "request-hostile",
                "model_tool_name": binding.model_name,
                "canonical_action": binding.canonical_action,
                "schema_fingerprint": binding.fingerprint,
                "turn_id": "turn-1",
                "session_id": "session-1",
                "workspace_id": "workspace-1",
                "tool_call_id": "call-hostile",
                "args": {"action": "list"},
            }
            before = len(calls)
            for key, bad in (
                ("canonical_action", "terminal"),
                ("schema_fingerprint", "bad"),
                ("turn_id", "other-turn"),
                ("model_tool_name", "skills_list"),
            ):
                hostile = dict(base)
                hostile[key] = bad
                result = invoke(hostile)
                assert result["ok"] is False, (surface, key, result)
                assert result["error_code"] == "tool_binding_error", (
                    surface,
                    key,
                    result,
                )
            assert len(calls) == before, calls

            tool_results = [line for line in watch_lines if line.startswith("TOOL_RESULT ")]
            assert tool_results, (surface, watch_lines)
            for line in tool_results:
                assert _TOOL_RESULT_RE.match(line), line
            ok_line = next(
                line for line in tool_results if f"model_tool_name={binding.model_name}" in line and " ok=true " in line
            )
            assert "error_code=-" in ok_line, ok_line
            assert "args=probe:" in next(
                line for line in tool_results if "args=probe:" in line
            )
            bad_line = next(line for line in tool_results if "ok=false" in line)
            assert "error_code=tool_binding_error" in bad_line, bad_line

    # Safe args summary never embeds values.
    summary = runtime_mod._safe_args_summary({"token": "supersecrettoken", "n": 12})
    assert summary == "n:2,token:16", summary
    assert "supersecrettoken" not in summary

    print("native_tool_binding ok")


if __name__ == "__main__":
    main()
