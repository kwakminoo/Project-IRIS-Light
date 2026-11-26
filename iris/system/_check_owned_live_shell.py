"""Live Owned shell.run roundtrip — no IRIS IDE / Cursor companion.

Asserts live ``iris_agent_repo_dir`` is owned, forces ``tool_choice=required``
in an isolated EngineHome, binds host ``shell.run``, requires the model to
call terminal once with ``echo <marker>``. Exit 0 when shell.run ok + marker.
Does not write live selection / hermes / migration.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from iris.engine import runtime
from iris.engine.types import (
    CancelToken,
    ChatTranscript,
    EngineHome,
    EnginePython,
    InternalSidecar,
    StatelessTurn,
    TurnFinished,
)
from iris.infrastructure.agent_runtime import (
    IRIS_AGENT_CHECKOUT_NAME,
    LEGACY_AGENT_CHECKOUT_NAME,
    _OWNED_SLOT_NAME,
    iris_agent_home,
    iris_agent_repo_dir,
)
from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
from iris.infrastructure.speak_capability import normalize_speak_invoke
from iris.system.win_subprocess import no_window_kwargs

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / ".tmp" / "owned-live-shell"
MODEL = "gpt-oss:20b"
LIVE_SELECTION = iris_agent_home() / "iris-engine-selection.json"


def _snapshot_selection() -> dict:
    exists = LIVE_SELECTION.is_file()
    return {
        "exists": exists,
        "text": LIVE_SELECTION.read_text(encoding="utf-8") if exists else None,
        "mtime": LIVE_SELECTION.stat().st_mtime if exists else None,
    }


def _assert_owned_repo(repo: Path) -> None:
    name = repo.name
    assert name != LEGACY_AGENT_CHECKOUT_NAME, f"live resolve is hermes recovery: {repo}"
    owned = name == IRIS_AGENT_CHECKOUT_NAME or bool(_OWNED_SLOT_NAME.fullmatch(name))
    assert owned, f"live resolve is not owned: {repo}"
    py = repo / "venv" / "Scripts" / "python.exe"
    assert py.is_file(), f"owned venv python missing: {py}"


def _seed_forced_tool_choice(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.yaml"
    try:
        import yaml  # type: ignore

        data: dict = {}
        if path.is_file():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
            if isinstance(loaded, dict):
                data = loaded
        agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
        agent["tool_choice"] = "required"
        data["agent"] = agent
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        path.write_text("agent:\n  tool_choice: required\n", encoding="utf-8")


def _shell_handler(marker: str, calls: list):
    def handler(action: str, args: dict) -> dict:
        key, payload = normalize_speak_invoke(action, dict(args or {}))
        if key != "shell.run":
            result = {"ok": False, "error": f"unexpected action {key}", "action": key}
            calls.append({"action": action, "normalized": key, "payload": payload, "result": result})
            return result
        command = str(payload.get("command") or "").strip()
        if not command:
            result = {"ok": False, "error": "empty command", "action": key}
            calls.append({"action": action, "normalized": key, "payload": payload, "result": result})
            return result
        completed = subprocess.run(
            ["cmd", "/c", command],
            capture_output=True,
            text=True,
            timeout=30,
            **no_window_kwargs(),
        )
        stdout = (completed.stdout or "") + (completed.stderr or "")
        result = {
            "ok": completed.returncode == 0 and marker in stdout,
            "action": key,
            "data": {
                "exit_code": completed.returncode,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "argv": ["cmd", "/c", command],
                "marker_seen": marker in stdout,
            },
        }
        calls.append({"action": action, "normalized": key, "payload": payload, "result": result})
        return result

    return handler


def main() -> int:
    before = _snapshot_selection()
    repo = iris_agent_repo_dir()
    _assert_owned_repo(repo)
    python = repo / "venv" / "Scripts" / "python.exe"

    home = OUT / "shell-home"
    home.mkdir(parents=True, exist_ok=True)
    _seed_forced_tool_choice(home)
    marker = "IRIS_OWNED_" + uuid.uuid4().hex[:12].upper()
    runtime._WATCH_LOG = home / "shell-watch.log"
    engine = runtime.Engine(InternalSidecar(home=EngineHome(home)))
    calls: list = []
    engine.bind_tool_handler(_shell_handler(marker, calls))
    prompt = (
        "Call the function tool named terminal exactly once now. "
        f'Arguments must include command="echo {marker}". '
        "Do not write markdown. Do not invent stdout. Wait for the tool result, "
        "then quote it verbatim."
    )
    turn = StatelessTurn(
        ChatTranscript.parse([{"role": "user", "content": prompt}]),
        resolve_iris_agent_inference(MODEL),
        CancelToken(),
        speak_surface="home",
    )
    eng_py = EnginePython(python)
    with (
        patch("iris.engine.runtime.engine_python", return_value=eng_py),
        patch("iris.engine._home.engine_python", return_value=eng_py),
        patch("iris.engine.runtime.probe_engine_python", return_value=None),
        patch("iris.engine.runtime._apply_ollama_options_guard_now", return_value=False),
    ):
        start = time.perf_counter()
        try:
            ready = engine.ensure_ready()
            startup = round(time.perf_counter() - start, 3)
            start = time.perf_counter()
            events = [(event, time.perf_counter() - start) for event in engine.run_turn(turn)]
        finally:
            engine.shutdown()

    finished = next((e.text for e, _ in events if isinstance(e, TurnFinished)), "")
    watch = ""
    watch_path = home / "shell-watch.log"
    if watch_path.is_file():
        watch = watch_path.read_text(encoding="utf-8", errors="replace")
    routed = "TOOL_ROUTE" in watch and ("shell.run" in watch or "terminal" in watch)
    shell_ok = any(
        c.get("normalized") == "shell.run"
        and isinstance(c.get("result"), dict)
        and c["result"].get("ok") is True
        and marker in json.dumps(c.get("payload") or {}, ensure_ascii=False)
        for c in calls
    )
    after = _snapshot_selection()
    evidence = {
        "shell_ok": shell_ok,
        "marker": marker,
        "routed": routed,
        "resolved_checkout": str(repo),
        "python": str(python),
        "model": MODEL,
        "ready": repr(ready),
        "startup_sec": startup,
        "seconds": round(events[-1][1], 3) if events else None,
        "events": [type(e).__name__ for e, _ in events],
        "terminal": repr(events[-1][0]) if events else None,
        "finished_preview": (finished or "")[:400],
        "tool_calls": calls,
        "forced_tool_choice": "required",
        "selection_untouched": before == after,
        "path": str(home),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in evidence.items() if k != "tool_calls"}, indent=2, ensure_ascii=False))
    print(json.dumps({"tool_calls": calls}, indent=2, ensure_ascii=False))
    return 0 if shell_ok and evidence["selection_untouched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
