"""Live Owned HELLO — no IRIS IDE / Cursor companion.

Asserts live ``iris_agent_repo_dir`` is an owned checkout (slot or canonical),
runs one Engine StatelessTurn on that venv, exits 0 when text contains
``IRIS-ACF-HELLO``. Isolated EngineHome under ``.tmp/owned-live-hello`` only.
Does not write live selection / hermes / migration.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from iris.engine import runtime
from iris.engine.types import (
    CancelToken,
    ChatTranscript,
    ContentDelta,
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

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / ".tmp" / "owned-live-hello"
MODEL = "gpt-oss:20b"
HELLO_TEXT = "IRIS-ACF-HELLO"
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


def main() -> int:
    before = _snapshot_selection()
    repo = iris_agent_repo_dir()
    _assert_owned_repo(repo)
    python = repo / "venv" / "Scripts" / "python.exe"

    home = OUT / "hello-home"
    home.mkdir(parents=True, exist_ok=True)
    runtime._WATCH_LOG = home / "hello-watch.log"
    engine = runtime.Engine(InternalSidecar(home=EngineHome(home)))
    turn = StatelessTurn(
        ChatTranscript.parse(
            [{"role": "user", "content": f"Reply with just this exact text: {HELLO_TEXT}"}]
        ),
        resolve_iris_agent_inference(MODEL),
        CancelToken(),
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
    first_delta = next((round(t, 3) for e, t in events if isinstance(e, ContentDelta)), None)
    ok = HELLO_TEXT in (finished or "")
    after = _snapshot_selection()
    evidence = {
        "hello_ok": ok,
        "resolved_checkout": str(repo),
        "python": str(python),
        "model": MODEL,
        "ready": repr(ready),
        "startup_sec": startup,
        "first_delta_sec": first_delta,
        "seconds": round(events[-1][1], 3) if events else None,
        "events": [type(e).__name__ for e, _ in events],
        "terminal": repr(events[-1][0]) if events else None,
        "selection_untouched": before == after,
        "path": str(home),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if ok and evidence["selection_untouched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
