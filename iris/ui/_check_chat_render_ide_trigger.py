"""연번 11 자검 — IDE 개방 트리거(도구 호출)와 채팅 표시(렌더러)의 계층 독립성.

1) 렌더러를 통과시켜도 동일 원문의 펜스 감지 결과가 불변 (연번 10 회귀 방지)
2) project.write_file 성공 표시가 서면 펜스가 와도 개방 시도 0회 (중복 개방 방지)
3) 표시가 없으면 펜스 감지가 종전과 동일 (폴백 소실 방지)
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from iris.system.project_ops import extract_first_code_block
from iris.ui.chat.chat_renderer import render_iris_message
from iris.ui.window.main_window import MainWindow

_BACKTICK3 = "```"

PROMPT = "간단한 파이썬 스크립트 하나 만들어줘"
ASSISTANT_RAW = (
    "요청한 스크립트입니다.\n\n"
    f"{_BACKTICK3}python\n"
    "for i in range(1, 10):\n"
    "    print(i)\n"
    f"{_BACKTICK3}\n\n"
    "실행은 IDE 통합 터미널에서 합니다.\n"
)


class _ChatStub:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def append_message_instant(self, who: str, text: str) -> None:
        self.messages.append(f"{who}: {text}")


class _TriggerProbe:
    """MainWindow의 라이브 vibe 경로만 떼어 구동한다 — 창·DB·IDE 없이 개방 시도를 계수."""

    _note_tool_file_write = MainWindow._note_tool_file_write
    _feed_live_vibe_stream = MainWindow._feed_live_vibe_stream
    _live_vibe_try_start = MainWindow._live_vibe_try_start
    _live_vibe_flush = MainWindow._live_vibe_flush
    _live_vibe_write = MainWindow._live_vibe_write
    _try_reveal_local_vibe_code = MainWindow._try_reveal_local_vibe_code

    def __init__(self) -> None:
        self._pending_local_vibe_prompt = PROMPT
        self._live_vibe: dict | None = None
        self._chat = _ChatStub()
        self.opens: list[str] = []

    def _live_vibe_open_target(self, state: dict, lang: str) -> bool:
        # 실제 구현은 project_root·바인딩 세션·파일 생성을 요구한다 — 여기선 계수만.
        self.opens.append(lang)
        return True

    def stream(self, text: str, *, chunk: int = 7) -> None:
        for idx in range(0, len(text), chunk):
            self._feed_live_vibe_stream(text[idx : idx + chunk])


def _detect() -> tuple[dict | None, list[str], bool]:
    probe = _TriggerProbe()
    probe.stream(ASSISTANT_RAW)
    state = probe._live_vibe or {}
    return extract_first_code_block(ASSISTANT_RAW), probe.opens, bool(state.get("finished"))


def _check_render_layer_is_independent() -> None:
    raw_before = ASSISTANT_RAW
    baseline = _detect()

    html = render_iris_message(ASSISTANT_RAW)
    assert "iris-copy://" in html, f"렌더러가 코드블록을 처리하지 않음: {html[:200]!r}"

    assert ASSISTANT_RAW == raw_before, "렌더러가 원문을 변형함"
    assert _detect() == baseline, "렌더 통과 후 펜스 감지 결과가 달라짐"
    assert baseline[1] == ["python"], f"기준 감지 실패: {baseline!r}"


def _check_tool_write_suppresses_fence() -> None:
    probe = _TriggerProbe()
    probe._note_tool_file_write()
    probe.stream(ASSISTANT_RAW)

    assert probe.opens == [], f"도구 표시 후에도 개방 시도 발생: {probe.opens!r}"
    state = probe._live_vibe or {}
    assert state.get("tool_written") is True, f"표시 누락: {state!r}"
    assert not state.get("started"), f"라이브 타이핑이 시작됨: {state!r}"

    probe._try_reveal_local_vibe_code(ASSISTANT_RAW)
    assert probe._chat.messages == [], f"사후 재생 폴백이 실행됨: {probe._chat.messages!r}"
    assert probe._pending_local_vibe_prompt == "", "턴 상태가 정리되지 않음"


def _check_fence_fallback_still_works() -> None:
    probe = _TriggerProbe()
    probe.stream(ASSISTANT_RAW)

    state = probe._live_vibe or {}
    assert probe.opens == ["python"], f"펜스 감지 폴백 소실: {probe.opens!r}"
    assert state.get("started") is True, f"라이브 타이핑 미시작: {state!r}"
    assert state.get("finished") is True, f"닫는 펜스 미처리: {state!r}"
    assert not state.get("tool_written"), "도구 표시가 잘못 섰음"

    probe._try_reveal_local_vibe_code(ASSISTANT_RAW)
    assert probe._chat.messages, "표시 없을 때 턴 종료 경로가 무동작"


def main() -> int:
    _check_render_layer_is_independent()
    _check_tool_write_suppresses_fence()
    _check_fence_fallback_still_works()
    print("chat render / ide trigger ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
