"""Sidecar turn idle budget must outlast long tool-arg generations."""

from __future__ import annotations

from iris.engine.runtime import _TURN_IDLE_SEC
from iris.engine.types import EngineError, EngineErrorCode
from iris.infrastructure.hermes_errors import explain_chat_error


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
    print("turn_idle self-check ok", _TURN_IDLE_SEC)


if __name__ == "__main__":
    main()
