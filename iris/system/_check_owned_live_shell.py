"""Owned sidecar + local model + normal SpeakTools and shell action (L3).

An in-process confirmation callback approves only the fixture command, and a
card recorder checks output at the shell presenter boundary. No live GUI or
Control HTTP is involved.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from iris.engine import runtime
from iris.engine._home import checkout_python
from iris.engine.types import (
    CancelToken,
    ChatTranscript,
    EngineHome,
    InternalSidecar,
    StatelessTurn,
    TurnFinished,
)
from iris.infrastructure.agent_runtime import iris_agent_home, iris_agent_repo_dir
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
from iris.infrastructure.speak_capability import bind_live_control_surface, set_speak_surface
from iris.system.control_surface import ActionRegistry
from iris.system.execution_runtime import ProcessRegistry
from iris.system.setup_protocol import HERMES_MIN_OLLAMA_NUM_CTX
from iris.ui.control_actions.shell import register_shell_actions

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / ".tmp" / "owned-live-shell"
MODEL = "gpt-oss:20b"


def _snapshot_selection() -> tuple[str, int] | None:
    path = iris_agent_home() / "iris-engine-selection.json"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8"), path.stat().st_mtime_ns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-choice", choices=("auto", "required"), default="required")
    mode = parser.parse_args().tool_choice
    before = _snapshot_selection()
    repo = iris_agent_repo_dir()
    python = checkout_python(repo)
    assert python is not None, f"Owned Python missing: {repo}"

    token = uuid.uuid4().hex
    home = OUT / mode / token
    workspace = home / "workspace"
    workspace.mkdir(parents=True)
    (home / "config.yaml").write_text(
        f"agent:\n  tool_choice: {mode}\nmodel:\n  ollama_num_ctx: {HERMES_MIN_OLLAMA_NUM_CTX}\n",
        encoding="utf-8",
    )
    marker = "IRIS_OWNED_" + uuid.uuid4().hex.upper()
    (workspace / "iris-grounding.txt").write_text(marker + "\n", encoding="utf-8")
    command = "type iris-grounding.txt" if os.name == "nt" else "cat iris-grounding.txt"
    args = {"command": command, "cwd": str(workspace)}
    evidence_path = OUT / f"{mode}-evidence.json"
    watch = home / "host-watch.log"
    turn_session = f"grounding-{token}"
    cards: list[dict] = []
    chat = SimpleNamespace(
        insert_tool_block=lambda **card: cards.append(card) or "fixture-card",
        replace_tool_block=lambda _block, **card: cards.append(card) or True,
    )
    window = SimpleNamespace(_ui_mode="home", _chat=chat, _conversation_id=turn_session)
    registry = ActionRegistry()
    register_shell_actions(window, registry)
    process = ProcessRegistry(runs_root=home / "runs")
    surface = SimpleNamespace(registry=registry, booting=False)
    engine = runtime.Engine(InternalSidecar(home=EngineHome(home)), staged_python=python)
    calls: list[tuple[str, dict]] = []

    def invoke(action: str, payload: dict) -> dict:
        result = (
            speak_invoke_agent_tool(action, payload)
            if action == "shell.run" else {"ok": False, "error": "fixture only permits shell.run"}
        )
        calls.append((action, result))
        return result

    engine.bind_tool_handler(invoke)
    request = (
        f'Use the local shell in directory "{workspace}" to run `{command}` once. '
        "Reply with the exact contents printed by the command, with no extra text."
    )
    if mode == "required":
        request = (
            f"Call terminal once with exactly these arguments: {json.dumps(args)}. "
            "Reply with the exact stdout text only."
        )
    turn = StatelessTurn(
        ChatTranscript.parse([{"role": "user", "content": request}]),
        resolve_iris_agent_inference(MODEL),
        CancelToken(),
        speak_surface="home",
        session_id=turn_session,
        workspace_id=str(workspace),
    )
    approval = Mock(side_effect=lambda spec, payload: spec.name == "shell.run" and payload == args)
    set_speak_surface("home")
    bind_live_control_surface(surface)
    try:
        with (
            patch.object(runtime, "_WATCH_LOG", watch),
            patch("iris.system.iris_shell.default_runtime", return_value=process),
            patch.dict(os.environ, {"IRIS_ENGINE_WATCH_LOG": str(home / "sidecar-watch.log")}),
        ):
            denied = speak_invoke_agent_tool("shell.run", args)
            forged = registry.invoke("shell.run", {**args, "confirm": True})
            denial_ok = all(
                out.get("ok") is False and "human confirm required" in out.get("error", "")
                for out in (denied, forged)
            )
            registry.set_human_confirm(approval)
            start = time.perf_counter()
            try:
                ready = engine.ensure_ready()
                startup = round(time.perf_counter() - start, 3)
                start = time.perf_counter()
                events = list(engine.run_turn(turn))
                elapsed = round(time.perf_counter() - start, 3)
            finally:
                engine.shutdown()
    finally:
        bind_live_control_surface(None)

    finished = next((event.text for event in events if isinstance(event, TurnFinished)), "")
    method, result = calls[0] if len(calls) == 1 else ("", {})
    data = result.get("data") or {}
    shell_ok = (
        method == "shell.run"
        and result.get("ok") is True
        and data.get("exit_code") == 0
        and data.get("stdout", "").strip() == marker
        and data.get("stderr") == ""
    )
    correlated = False
    if watch.is_file():
        for line in watch.read_text(encoding="utf-8").splitlines():
            if "TOOL_RESULT " not in line or "action=shell.run ok=true" not in line:
                continue
            fields = dict(field.split("=", 1) for field in line.split("TOOL_RESULT ", 1)[1].split())
            id_pair = f"request_id={fields['request_id']} tool_call_id={fields['tool_call_id']}"
            correlated = fields["tool_call_id"] != "-" and any(
                "TOOL_CALL " + id_pair in record
                and f"session_id={turn_session}" in record
                and f"workspace_id={workspace}" in record
                for path in (home / "logs").glob("sidecar-*.log")
                for record in path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
    proof = {
        "approval_applied": denial_ok and approval.call_count == 1,
        "tool_correlation_ok": correlated,
        "stdout_and_stderr_verified": shell_ok,
        "finished_exactly": finished.strip() == marker,
        "card_output_verified": any(
            card.get("phase") == "done" and marker in card.get("output", "") for card in cards
        ),
        "selection_untouched": before == _snapshot_selection(),
    }
    evidence = {
        **proof,
        "marker": marker,
        "resolved_checkout": str(repo),
        "python": str(python),
        "model": MODEL,
        "ready": repr(ready),
        "startup_sec": startup,
        "seconds": elapsed,
        "events": [type(event).__name__ for event in events],
        "terminal": repr(events[-1]) if events else None,
        "tool_calls": calls,
        "tool_choice": mode,
        "configured_num_ctx": HERMES_MIN_OLLAMA_NUM_CTX,
        "path": str(home),
    }
    text = json.dumps(evidence, indent=2)
    (home / "evidence.json").write_text(text, encoding="utf-8")
    evidence_path.write_text(text, encoding="utf-8")
    if mode == "required":
        (OUT / "evidence.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if all(proof.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
