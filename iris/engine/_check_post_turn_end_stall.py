"""Host must get done/fail soon after Hermes logs Turn ended, even if run_conversation hangs.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_post_turn_end_stall
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import iris.engine._sidecar_main as sidecar


class _HungAfterTurnEndAgent:
    """Fake Hermes: stream text, log Turn ended, then never return."""

    def __init__(self, **kwargs: Any) -> None:
        self._stream = kwargs.get("stream_delta_callback")
        self._persist_disabled = False
        self._block = threading.Event()

    def run_conversation(
        self,
        user_message: str = "",
        conversation_history: list | None = None,
        **_kwargs: Any,
    ) -> dict:
        if callable(self._stream):
            self._stream("assistant landed")
        logging.getLogger("agent.conversation_loop").info(
            "Turn ended: reason=text_response(finish_reason=stop) model=stub "
            "api_calls=1/1 budget=1/1 tool_turns=0 last_msg_role=assistant "
            "response_len=16 session=stub"
        )
        self._block.wait(30.0)
        return {"final_response": "should never be seen"}


class _HungFileOnlyTurnEndAgent:
    """Turn ended only on disk (no logging.Handler). Simulates Hermes reconfig."""

    def __init__(self, **kwargs: Any) -> None:
        self._stream = kwargs.get("stream_delta_callback")
        self._persist_disabled = False
        self._block = threading.Event()

    def run_conversation(
        self,
        user_message: str = "",
        conversation_history: list | None = None,
        **_kwargs: Any,
    ) -> dict:
        if callable(self._stream):
            self._stream("file-landed")
        path = os.environ.get("IRIS_ENGINE_LOG", "").strip()
        assert path, "IRIS_ENGINE_LOG required for file-only case"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(
                "Turn ended: reason=text_response(finish_reason=stop) model=stub "
                "api_calls=1/1 budget=1/1 tool_turns=0 last_msg_role=assistant "
                "response_len=11 session=file-only\n"
            )
            fh.flush()
        self._block.wait(30.0)
        return {"final_response": "should never be seen"}


class _QuickAgent:
    def __init__(self, **kwargs: Any) -> None:
        self._persist_disabled = False

    def run_conversation(
        self,
        user_message: str = "",
        conversation_history: list | None = None,
        **_kwargs: Any,
    ) -> dict:
        logging.getLogger("agent.conversation_loop").info(
            "Turn ended: reason=text_response(finish_reason=stop) model=stub "
            "api_calls=1/1 budget=1/1 tool_turns=0 last_msg_role=assistant "
            "response_len=5 session=stub"
        )
        return {"final_response": "quick"}


def _with_emit_capture(events: list[dict], body: object, emit=None) -> None:
    previous_grace = sidecar._POST_TURN_END_GRACE_SEC
    previous_poll = sidecar._TURN_ENDED_LOG_POLL_SEC
    sidecar._POST_TURN_END_GRACE_SEC = 0.2
    sidecar._TURN_ENDED_LOG_POLL_SEC = 0.05
    original_emit = sidecar._emit

    def capture(payload: dict) -> None:
        events.append(dict(payload))

    sidecar._emit = emit or capture  # type: ignore[method-assign]
    try:
        body()
    finally:
        sidecar._emit = original_emit  # type: ignore[method-assign]
        sidecar._POST_TURN_END_GRACE_SEC = previous_grace
        sidecar._TURN_ENDED_LOG_POLL_SEC = previous_poll


def main() -> None:
    hung_events: list[dict] = []
    started = time.monotonic()

    def hung_body() -> None:
        sidecar._run_agent_turn(_HungAfterTurnEndAgent, [], "ping", {})

    _with_emit_capture(hung_events, hung_body)
    elapsed = time.monotonic() - started
    terminal = next(
        (row for row in hung_events if row.get("t") in ("done", "fail")),
        None,
    )
    assert terminal is not None, f"no done/fail after Turn ended; events={hung_events!r}"
    assert terminal.get("t") == "done", terminal
    assert terminal.get("text") == "assistant landed", terminal
    assert elapsed < 2.0, elapsed

    quick_events: list[dict] = []

    def quick_body() -> None:
        sidecar._run_agent_turn(_QuickAgent, [], "ping", {})

    _with_emit_capture(quick_events, quick_body)
    dones = [row for row in quick_events if row.get("t") == "done"]
    assert len(dones) == 1, quick_events
    assert dones[0].get("text") == "quick", dones[0]

    # First done write fails like Windows OSError 22 inside Handler.emit;
    # gate must clear so a later emit (retry / return path) still lands.
    flaky_events: list[dict] = []
    blows = {"n": 0}

    def flaky_emit(payload: dict) -> None:
        if payload.get("t") == "done":
            blows["n"] += 1
            if blows["n"] == 1:
                raise OSError(22, "Invalid argument")
        flaky_events.append(dict(payload))

    def flaky_body() -> None:
        sidecar._run_agent_turn(_HungAfterTurnEndAgent, [], "ping", {})

    _with_emit_capture(flaky_events, flaky_body, emit=flaky_emit)
    flaky_done = next(
        (row for row in flaky_events if row.get("t") == "done"),
        None,
    )
    assert flaky_done is not None, f"no done after OSError; events={flaky_events!r}"
    assert flaky_done.get("text") == "assistant landed", flaky_done
    assert blows["n"] >= 2, blows

    file_events: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "engine.log"
        log_path.write_text("", encoding="utf-8")
        previous_log = os.environ.get("IRIS_ENGINE_LOG")
        os.environ["IRIS_ENGINE_LOG"] = str(log_path)
        file_started = time.monotonic()

        def file_body() -> None:
            sidecar._run_agent_turn(_HungFileOnlyTurnEndAgent, [], "ping", {})

        try:
            _with_emit_capture(file_events, file_body)
        finally:
            if previous_log is None:
                os.environ.pop("IRIS_ENGINE_LOG", None)
            else:
                os.environ["IRIS_ENGINE_LOG"] = previous_log
        file_elapsed = time.monotonic() - file_started

    file_done = next(
        (row for row in file_events if row.get("t") in ("done", "fail")),
        None,
    )
    assert file_done is not None, f"no done after file-only Turn ended; events={file_events!r}"
    assert file_done.get("t") == "done", file_done
    assert file_done.get("text") == "file-landed", file_done
    assert file_elapsed < 2.0, file_elapsed

    print(
        "post_turn_end_stall self-check ok",
        round(elapsed, 3),
        round(file_elapsed, 3),
    )


if __name__ == "__main__":
    main()
