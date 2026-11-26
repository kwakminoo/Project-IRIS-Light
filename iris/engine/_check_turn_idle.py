"""Sidecar turn idle budget must outlast long tool-arg generations."""

from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from iris.engine import CancelToken, ContentDelta, Engine, EngineHome, InternalSidecar, TurnFinished
from iris.engine import runtime
from iris.engine.runtime import _TURN_IDLE_SEC
from iris.engine.types import EngineError, EngineErrorCode
from iris.infrastructure.iris_agent_errors import explain_chat_error


def _check_stdout_survives_terminal_file_between_turns() -> None:
    source: Queue[str] = Queue()
    first_read = Event()

    def readline() -> str:
        first_read.set()
        return source.get(timeout=3.0)

    def first_terminal(_pid: int, **_kwargs: object) -> str:
        assert first_read.wait(1.0)
        return '{"t":"done","turn_id":"one","text":"first"}\n'

    child = SimpleNamespace(stdout=SimpleNamespace(readline=readline), poll=lambda: None)
    engine = Engine(InternalSidecar(EngineHome(Path.cwd())))
    try:
        with (
            patch.object(runtime, "_watch_trace"),
            patch.object(runtime, "_read_terminal_file_impl", side_effect=first_terminal),
        ):
            assert list(engine._read_turn_events(child, CancelToken(), turn_id="one")) == [
                TurnFinished("first")
            ]
        source.put('{"t":"delta","turn_id":"one","text":"late draft"}\n')
        source.put('{"t":"delta","turn_id":"two","text":"next chunk"}\n')
        source.put('{"t":"done","turn_id":"two","text":"second"}\n')
        with (
            patch.object(runtime, "_watch_trace"),
            patch.object(runtime, "_TURN_IDLE_SEC", 1),
        ):
            assert list(engine._read_turn_events(child, CancelToken(), turn_id="two")) == [
                ContentDelta("next chunk"), TurnFinished("second")
            ]
    finally:
        source.put("")


def main() -> None:
    timeout_ui = "응답 대기 시간이 초과됐습니다. 잠시 후 다시 시도하세요."
    assert _TURN_IDLE_SEC >= 600.0, _TURN_IDLE_SEC
    idle = EngineError(EngineErrorCode.TURN_IDLE, "sidecar event timed out")
    assert idle.user_message == timeout_ui
    assert explain_chat_error(idle.user_message) == timeout_ui
    assert explain_chat_error("엔진 응답을 읽지 못했습니다.") == timeout_ui
    assert "요청을 처리하지 못했습니다" not in explain_chat_error(
        "엔진 응답을 읽지 못했습니다."
    )
    _check_stdout_survives_terminal_file_between_turns()
    print("turn_idle self-check ok", _TURN_IDLE_SEC)


if __name__ == "__main__":
    main()
