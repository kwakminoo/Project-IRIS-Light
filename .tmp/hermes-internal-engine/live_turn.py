"""Headless EngineHome turn. Not imported by IRIS."""

from __future__ import annotations

import sys

from iris.engine.runtime import reset_shared_engine, shared_engine
from iris.engine.types import CancelToken, ChatTranscript, EngineFailed, StatelessTurn
from iris.infrastructure.hermes_client import HermesInferenceTarget


def _show(event: object) -> None:
    extra = (
        getattr(event, "text", None)
        or getattr(event, "label", None)
        or getattr(event, "error", None)
    )
    line = f"{type(event).__name__} {extra}"
    sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def main() -> int:
    reset_shared_engine()
    eng = shared_engine()
    ready = eng.ensure_ready()
    _show(ready)
    if isinstance(ready, EngineFailed):
        return 2
    turn = StatelessTurn(
        transcript=ChatTranscript.parse(
            [{"role": "user", "content": "Reply with the single word pong."}]
        ),
        model=HermesInferenceTarget(
            model="gemma4:e2b",
            provider="custom",
            base_url="http://127.0.0.1:11434/v1",
        ),
        cancel=CancelToken(),
    )
    for event in eng.run_turn(turn):
        _show(event)
    eng.shutdown()
    sys.stdout.buffer.write(b"CHILD_AFTER gone\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
