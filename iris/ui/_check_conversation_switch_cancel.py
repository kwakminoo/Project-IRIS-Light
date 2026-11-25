"""생성 중 대화 전환 — 워커는 계속되고, 토큰은 그 대화에만 붙는다.

Visible transcript is H1 `_turns`, not hidden `_log`.
Restore must not call sync `_run_js_sync` once per message (UI freeze).
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

from iris.runtime.chat_run_slot import ChatRunMap
from iris.runtime.turn_followthrough import CAP
from iris.storage.conversations import history_dicts

_APP = QApplication.instance() or QApplication(sys.argv)


class _Worker:
    def __init__(self) -> None:
        self.cancelled = False

    def request_cancel(self) -> None:
        self.cancelled = True

    def isRunning(self) -> bool:  # noqa: N802
        return True

    def wait(self, _ms: int = 0) -> bool:
        return True


def _assistant(db, cid: int) -> str:
    parts = [
        item["content"]
        for item in history_dicts(db, cid)
        if item["role"] == "assistant"
    ]
    return "\n".join(parts)


def _h1_text(chat) -> str:
    """Visible transcript text from H1 turns (not hidden `_log`)."""
    chunks: list[str] = []
    for turn in chat.transcript()._turns:
        for part in turn.parts:
            md = getattr(part, "markdown", None)
            if md:
                chunks.append(str(md))
            body = getattr(part, "body", None)
            if body:
                chunks.append(str(body))
            src = getattr(part, "source", None)
            if src:
                chunks.append(str(src))
    return "\n".join(chunks)


def check_conversation_switch_updates_h1_turns() -> None:
    """Restore lands on H1 `_turns`; switch must not leave stale turns painted in memory."""
    from iris.ui.chat.chat_panel import ChatPanel

    panel = ChatPanel()
    panel.restore_messages(
        [
            {"role": "user", "content": "ALPHA-USER"},
            {"role": "assistant", "content": "ALPHA-ASSIST"},
        ]
    )
    shown = _h1_text(panel)
    assert "ALPHA-USER" in shown, shown
    assert "ALPHA-ASSIST" in shown, shown
    assert len(panel.transcript()._turns) == 2

    panel.restore_messages(
        [
            {"role": "user", "content": "BETA-ONLY"},
        ]
    )
    shown_b = _h1_text(panel)
    assert "BETA-ONLY" in shown_b, shown_b
    assert "ALPHA-USER" not in shown_b, shown_b
    assert "ALPHA-ASSIST" not in shown_b, shown_b
    assert len(panel.transcript()._turns) == 1
    panel.close()


def check_restore_avoids_per_message_js_sync() -> None:
    """Restore must not schedule per-message scroll (each hits `_run_js_sync` / QEventLoop)."""
    from iris.ui.chat.chat_panel import ChatPanel

    _ = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    host = panel.transcript()
    scroll_calls: list[bool] = []
    render_calls = {"n": 0}

    def _count_scroll(*, deferred: bool = False) -> None:
        scroll_calls.append(bool(deferred))
        # Skip real scroll: would `_run_js_sync` → nested QEventLoop on UI thread.

    def _count_render() -> None:
        render_calls["n"] += 1

    panel._scroll_log_to_bottom = _count_scroll  # type: ignore[method-assign]
    host._render = _count_render  # type: ignore[method-assign]
    n = 8
    messages = []
    for i in range(n):
        messages.append({"role": "user", "content": f"U{i}"})
        messages.append({"role": "assistant", "content": f"A{i}"})
    panel.restore_messages(messages)
    assert len(scroll_calls) <= 1, (
        f"restore scheduled scroll {len(scroll_calls)} times "
        f"(want <=1 for {n * 2} messages)"
    )
    # clear + one batch land (not one _render per message)
    assert render_calls["n"] <= 2, (
        f"restore _render count={render_calls['n']} (want <=2: clear + batch)"
    )
    assert len(host._turns) == n * 2
    assert "U0" in _h1_text(panel) and f"A{n - 1}" in _h1_text(panel)
    panel.close()


def main() -> None:
    from iris.ui.window.main_window import MainWindow

    check_conversation_switch_updates_h1_turns()
    check_restore_avoids_per_message_js_sync()

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(test_mode=True)
    assert isinstance(win._runs, ChatRunMap)
    assert win._runs.slot(win._conversation_id).conversation_id == win._conversation_id
    assert CAP == 8
    win.show()
    app.processEvents()

    session = win._chat_session
    a = win._conversation_id
    win._record_history("user", "과일을 주제로 짧은 설명")
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("1. 과일 설명\n")
    worker = _Worker()
    win._chat_worker = worker
    gate = win._turn_gate
    gate.begin("turn-a")
    gate.arm()

    b = session.start_new()
    assert b != a
    win._on_conversation_selected(b)
    app.processEvents()

    assert not worker.cancelled
    assert win._conversation_id == b
    assert win._runs.slot(a).gate.is_current("turn-a")
    assert win._runs.slot(a).gate.busy
    assert not win._busy
    assert "과일" not in _h1_text(win._chat)

    before_b = history_dicts(win._db, b)
    win._on_content_chunk_for_turn("HIDDEN-TOKEN", "turn-a")
    app.processEvents()
    assert "HIDDEN-TOKEN" not in _h1_text(win._chat)
    assert "HIDDEN-TOKEN" in win._runs.slot(a).pending_partial
    assert history_dicts(win._db, b) == before_b

    from iris.runtime.user_turn import UserTurn, UserTurnSource

    win._runs.slot(b).pending_past_chats = "B-PAST-EVIDENCE"
    real_launch = win._launch_chat_turn
    win._launch_chat_turn = lambda *_args, **_kwargs: None
    try:
        recorded = UserTurn(
            text="A1x",
            source=UserTurnSource.KEYBOARD,
            session_id=a,
            id="turn-a",
        )
        win._commit_recorded_user_turn(recorded, "test-model", "A1x", True)
    finally:
        win._launch_chat_turn = real_launch
    app.processEvents()
    assert "A1x" not in _h1_text(win._chat)
    users_a = [
        item["content"] for item in history_dicts(win._db, a) if item["role"] == "user"
    ]
    users_b = [
        item["content"] for item in history_dicts(win._db, b) if item["role"] == "user"
    ]
    assert "A1x" in users_a
    assert "A1x" not in users_b
    assert win._runs.slot(a).pending_past_chats != win._runs.slot(b).pending_past_chats
    assert win._runs.slot(b).pending_past_chats == "B-PAST-EVIDENCE"

    win._on_chat_finished_for_turn("A의 끝난 답", "turn-a")
    app.processEvents()
    assert not worker.cancelled
    assert history_dicts(win._db, b) == before_b
    assert "A의 끝난 답" in _assistant(win._db, a)
    assert "A의 끝난 답" not in _h1_text(win._chat)
    assert not win._runs.slot(a).gate.busy
    assert win._conversation_id == b

    win._runs.slot(a).followthrough_count = 4
    win._runs.slot(b).followthrough_count = 1
    win._on_conversation_selected(a)
    app.processEvents()
    assert win._followthrough_count == 4
    assert win._runs.slot(b).followthrough_count == 1
    shown = _h1_text(win._chat)
    assert "A의 끝난 답" in shown
    assert "HIDDEN-TOKEN" not in shown

    other = _Worker()
    win._runs.slot(b).worker = other
    win._runs.slot(b).gate.begin("turn-b")
    win._runs.slot(b).gate.arm()
    win._on_chat_stop()
    app.processEvents()
    assert not other.cancelled
    assert win._runs.slot(b).gate.busy

    import iris.ui.settings.hud_dialog as hud_dialog
    from iris.storage.conversations import create_conversation

    hud_dialog.run_hud_confirm = lambda *_args, **_kwargs: True
    keeper_id = int(create_conversation(win._db).id)
    keeper = _Worker()
    alive = _Worker()
    gone = _Worker()
    win._runs.slot(keeper_id).worker = keeper
    win._runs.slot(a).worker = alive
    win._runs.slot(b).worker = gone
    viewing = win._conversation_id
    win._on_conversation_deleted(b)
    app.processEvents()
    assert not alive.cancelled
    assert gone.cancelled
    assert not keeper.cancelled
    assert win._conversation_id == viewing
    win._on_conversation_deleted(a)
    app.processEvents()
    assert alive.cancelled
    assert not keeper.cancelled
    assert win._conversation_id != a

    win.close()
    app.processEvents()
    print("conversation switch keeps background run ok")


if __name__ == "__main__":
    main()
