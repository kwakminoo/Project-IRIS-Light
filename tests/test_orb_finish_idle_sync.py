from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

from iris.audio.mic_state import MicState
from iris.core.state_machine import AppState, StateMachine
import iris.engine as _engine
from iris.engine.types import ReasoningDelta as _ReasoningDelta
from iris.runtime import UserTurnDispatcher
from iris.runtime.chat_turn_gate import ChatTurnGate
from iris.runtime.user_turn import UserTurnSource

# hermes_workers imports ReasoningDelta; package __init__ does not export it yet.
_engine.ReasoningDelta = _ReasoningDelta

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.window.main_window import MainWindow


class _ChatStub:
    def set_generating(self, _generating: bool) -> None:
        return

    def set_presenting(self, _presenting: bool) -> None:
        return

    def is_typing_active(self) -> bool:
        return False


class _StatusHeaderStub:
    def set_app_state(self, _state: AppState, label: str = "") -> None:
        return


class _SttQueueStub:
    def is_busy(self) -> bool:
        return False

    def pending_count(self) -> int:
        return 0


class OrbFinishIdleSyncTests(TestCase):
    def setUp(self) -> None:
        self.h = SimpleNamespace()
        self.h._conversation_id = 7
        self.h._turn_dispatcher = UserTurnDispatcher(max_pending=4)
        self.h._turn_gate = ChatTurnGate()
        self.h._turn_worker_meta = {}
        self.h._state = StateMachine()
        self.h._status_header = _StatusHeaderStub()
        self.h._chat = _ChatStub()
        self.h._stt_queue = _SttQueueStub()
        self.h._mic = SimpleNamespace(state=MicState.OFF)
        self.h._busy = False
        self.h._tts_active_play = False
        self.h._tts_queue = []
        self.h._mic_listen_active = False
        self.h._pending_handoff = "x"
        self.h._pending_handoff_ctx = object()
        self.h._pending_past_chats = "x"
        self.h._pending_wiki_notes = "x"
        self.h._pending_code_notes = "x"
        self.h._pending_web_evidence = "x"
        self.h._turn_web_error = True
        self.h._turn_search_failure_reply = "x"
        self.h._stop_agent_log_activity = lambda: None
        self.h._slot_now = lambda: SimpleNamespace(conversation_id=self.h._conversation_id)
        self.h._showing_bound = lambda: True
        self.h._sync_chat_stop_for_presentation = lambda: MainWindow._sync_chat_stop_for_presentation(self.h)
        self.h._tts_busy = lambda: False
        self.h._workspace_chat_busy = lambda: False
        self.h._active_workspace_iris_panel = lambda: None
        self.h._mirror_voice_listening_status = lambda _text: None
        self.h._open_voice_followup_window = lambda: None
        self.h._on_chat_turn_finished = lambda _cid: None
        self.h._sync_voice_conversation_state = lambda: MainWindow._sync_voice_conversation_state(self.h)
        self.h._finish_current_turn = lambda turn_id=None, *, open_followup=False: MainWindow._finish_current_turn(
            self.h, turn_id, open_followup=open_followup
        )

    def test_finish_current_turn_leaves_idle_after_deferred_dispatcher_clear(self) -> None:
        turn = self.h._turn_dispatcher.submit(
            text="안녕",
            source=UserTurnSource.KEYBOARD,
            session_id=self.h._conversation_id,
        )
        assert turn is not None
        self.h._turn_gate.begin(turn.id)
        self.h._turn_gate.arm()
        self.h._state.set_state(AppState.PROCESSING)

        self.h._finish_current_turn(turn.id, open_followup=False)
        QCoreApplication.processEvents()

        self.assertEqual(self.h._state.state, AppState.IDLE)
        self.assertFalse(self.h._turn_dispatcher.is_session_busy(self.h._conversation_id))
