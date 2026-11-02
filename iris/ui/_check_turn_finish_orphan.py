"""같은 대화 promote 직후 owning=None finished_ok가 DB에 남는지.

구동작: owning이 없으면 return → assistant 유실.
신동작: (1) finish promote는 QTimer 한 틱 뒤 (2) meta 있으면 orphan persist.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.runtime import UserTurnSource
from iris.storage.conversations import history_dicts


def _check_deferred_promote(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()

    sync_calls: list[str] = []
    real = win._turn_dispatcher.finish_active_turn

    def _spy(turn_id=None):
        sync_calls.append(str(turn_id or ""))
        return real(turn_id)

    win._turn_dispatcher.finish_active_turn = _spy  # type: ignore[method-assign]
    try:
        win._turn_dispatcher.turn_ready.disconnect(win._dispatch_user_turn)
    except TypeError:
        pass
    turn = win._turn_dispatcher.submit(
        text="orphan-defer-a",
        source=UserTurnSource.KEYBOARD,
        session_id=int(win._conversation_id),
    )
    assert turn is not None
    win._turn_gate.begin(turn.id)
    win._turn_gate.arm()
    sync_calls.clear()

    win._finish_current_turn(turn.id, open_followup=False)
    assert sync_calls == [], f"promote must not run on finish stack: {sync_calls}"
    app.processEvents()
    assert sync_calls == [turn.id], f"promote after tick: {sync_calls}"
    win.close()
    app.processEvents()


def _check_orphan_persist(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "orphan-user")
    orphan_tid = "turn-orphan-b"
    reply = "orphan assistant reply that must land"
    win._turn_worker_meta[orphan_tid] = cid
    # owning None: gate holds another turn
    win._turn_gate.begin("turn-other")
    win._turn_gate.arm()
    assert win._runs.owning(orphan_tid) is None

    before = history_dicts(win._db, cid)
    win._on_chat_finished_for_turn(reply, orphan_tid)
    app.processEvents()
    after = history_dicts(win._db, cid)
    texts = [row["content"] for row in after]
    assert reply in texts, texts
    assert len(after) == len(before) + 1
    assert orphan_tid not in win._turn_worker_meta
    win.close()
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    _check_deferred_promote(app)
    _check_orphan_persist(app)
    print("turn finish orphan ok")


if __name__ == "__main__":
    main()
