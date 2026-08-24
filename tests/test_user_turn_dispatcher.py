from __future__ import annotations

import sys
from unittest import TestCase

from PyQt6.QtWidgets import QApplication

from iris.runtime import UserTurnDispatcher, UserTurnSource

_APP = QApplication.instance() or QApplication(sys.argv)


class UserTurnDispatcherTests(TestCase):
    def setUp(self) -> None:
        self.dispatcher = UserTurnDispatcher(max_pending=3)
        self.ready: list[object] = []
        self.queued: list[tuple[object, str]] = []
        self.dropped: list[tuple[object, str]] = []
        self.dispatcher.turn_ready.connect(self.ready.append)
        self.dispatcher.turn_queued.connect(lambda turn, reason: self.queued.append((turn, reason)))
        self.dispatcher.turn_dropped.connect(lambda turn, reason: self.dropped.append((turn, reason)))

    def test_idle_submit_dispatches_immediately(self) -> None:
        turn = self.dispatcher.submit(text="안녕 아이리스", source=UserTurnSource.VOICE, session_id=7)
        self.assertIsNotNone(turn)
        self.assertEqual(len(self.ready), 1)
        self.assertEqual(self.ready[0].text, "안녕 아이리스")
        self.assertEqual(self.ready[0].source, UserTurnSource.VOICE)
        self.assertEqual(self.ready[0].session_id, 7)
        self.assertEqual(self.dispatcher.pending_count(), 0)

    def test_busy_submit_waits_until_finish(self) -> None:
        first = self.dispatcher.submit(text="A", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="B", source=UserTurnSource.VOICE, session_id=3)
        self.assertEqual(len(self.ready), 1)
        self.assertEqual(self.dispatcher.pending_count(), 1)
        self.dispatcher.finish_active_turn(first.id)
        self.assertEqual(len(self.ready), 2)
        self.assertEqual(self.ready[1].text, "B")
        self.assertEqual(self.ready[1].source, UserTurnSource.VOICE)

    def test_queue_preserves_fifo_order(self) -> None:
        first = self.dispatcher.submit(text="A", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="B", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="C", source=UserTurnSource.KEYBOARD)
        self.dispatcher.finish_active_turn(first.id)
        second = self.ready[-1]
        self.dispatcher.finish_active_turn(second.id)
        third = self.ready[-1]
        self.assertEqual([turn.text for turn in self.ready], ["A", "B", "C"])
        self.dispatcher.finish_active_turn(third.id)
        self.assertEqual(self.dispatcher.pending_count(), 0)

    def test_overflow_emits_dropped_signal(self) -> None:
        self.dispatcher.submit(text="A", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="B", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="C", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="D", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="E", source=UserTurnSource.KEYBOARD)
        self.assertEqual(len(self.dropped), 1)
        self.assertEqual(self.dropped[0][0].text, "B")
        self.assertEqual(self.dropped[0][1], "queue_overflow")

    def test_clear_pending_returns_items(self) -> None:
        self.dispatcher.submit(text="A", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="B", source=UserTurnSource.KEYBOARD)
        self.dispatcher.submit(text="C", source=UserTurnSource.KEYBOARD)
        dropped = self.dispatcher.clear_pending()
        self.assertEqual([turn.text for turn in dropped], ["B", "C"])
        self.assertEqual(self.dispatcher.pending_count(), 0)
