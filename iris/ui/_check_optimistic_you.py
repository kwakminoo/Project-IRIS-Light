"""Optimistic You: latch + early present before AttachmentWorker, no double append."""

from __future__ import annotations

import inspect
import types

from iris.runtime.user_turn import UserTurn, UserTurnSource
from iris.ui.window.main_window import MainWindow


class _FakeChat:
    def __init__(self) -> None:
        self.appends: list[tuple[str, str]] = []

    def append_message_instant(self, who: str, text: str) -> None:
        self.appends.append((who, text))


class _FakeActivity:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append_instant_line(self, line: str) -> None:
        self.lines.append(line)


def _stub_window(*, conversation_id: int = 1) -> types.SimpleNamespace:
    win = types.SimpleNamespace(
        _turn_is_followthrough=False,
        _sending_followthrough=False,
        _conversation_id=conversation_id,
        _chat=_FakeChat(),
        _live_activity=_FakeActivity(),
    )
    win._active_workspace_iris_panel = lambda: None  # type: ignore[attr-defined]
    win._format_user_turn_content = lambda turn: (turn.text or "").strip() or "(attach)"  # type: ignore[attr-defined]
    win._present_user_turn_early = types.MethodType(  # type: ignore[attr-defined]
        MainWindow._present_user_turn_early, win
    )
    return win


def _check_mark_latch() -> None:
    turn = UserTurn(text="hi", source=UserTurnSource.KEYBOARD)
    assert turn.user_bubble_shown is False
    assert turn.mark_user_bubble_shown() is True
    assert turn.user_bubble_shown is True
    assert turn.mark_user_bubble_shown() is False
    assert turn.user_bubble_shown is True


def _check_present_idempotent() -> None:
    win = _stub_window()
    turn = UserTurn(text="hello", source=UserTurnSource.KEYBOARD, session_id=1)
    assert win._present_user_turn_early(turn) is True
    assert turn.user_bubble_shown is True
    assert win._chat.appends == [("You", "hello")]
    assert win._present_user_turn_early(turn) is False
    assert win._chat.appends == [("You", "hello")]


def _check_present_skips_voice_followthrough_session() -> None:
    win = _stub_window()
    voice = UserTurn(text="voice", source=UserTurnSource.VOICE, session_id=1)
    assert win._present_user_turn_early(voice) is False
    assert voice.user_bubble_shown is False

    win._turn_is_followthrough = True
    ft = UserTurn(text="ft", source=UserTurnSource.KEYBOARD, session_id=1)
    assert win._present_user_turn_early(ft) is False
    win._turn_is_followthrough = False

    other = UserTurn(text="other", source=UserTurnSource.KEYBOARD, session_id=99)
    assert win._present_user_turn_early(other) is False
    assert win._chat.appends == []


def _check_body_orders_present_before_attachment_worker() -> None:
    src = inspect.getsource(MainWindow._execute_user_turn_body)
    i_present = src.index("_present_user_turn_early")
    i_worker = src.index("AttachmentWorker")
    assert i_present < i_worker, "You must present before AttachmentWorker.start path"


def _check_continue_skips_when_shown() -> None:
    src = inspect.getsource(MainWindow._continue_user_turn_bound)
    assert "not turn.user_bubble_shown" in src
    assert "mark_user_bubble_shown" in src


def main() -> None:
    _check_mark_latch()
    _check_present_idempotent()
    _check_present_skips_voice_followthrough_session()
    _check_body_orders_present_before_attachment_worker()
    _check_continue_skips_when_shown()
    print("optimistic you ok")


if __name__ == "__main__":
    main()
