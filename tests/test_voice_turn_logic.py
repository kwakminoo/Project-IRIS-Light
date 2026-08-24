from __future__ import annotations

from collections import deque
import sys
import time
from types import SimpleNamespace
from unittest import TestCase

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

from iris.runtime import UserTurnDispatcher
from iris.storage.voice_prefs import VoicePreferences

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.window.main_window import MainWindow


class _LiveActivityStub:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append_instant_line(self, line: str) -> None:
        self.lines.append(line)


class _ChatStub:
    def __init__(self, draft: str = "") -> None:
        self.typing_buffer_text = ""
        self._draft = draft
        self.status = ""

    def current_input_text(self) -> str:
        return self._draft

    def set_user_listening_status(self, text: str) -> None:
        self.status = text


class VoiceTurnLogicTests(TestCase):
    def setUp(self) -> None:
        self.h = SimpleNamespace()
        self.h._voice_prefs = VoicePreferences()
        self.h._turn_dispatcher = UserTurnDispatcher(max_pending=4)
        self.h._recent_voice_turns = deque()
        self.h._voice_followup_deadline = 0.0
        self.h._last_tts_playback_ended_at = 0.0
        self.h._last_assistant_text = ""
        self.h._tts_active_play = False
        self.h._tts_queue = []
        self.h._busy = False
        self.h._chat = _ChatStub(draft="보고서 작성 중")
        self.h._live_activity = _LiveActivityStub()
        self.h._cancel_calls: list[tuple[str, bool]] = []
        self.h._cancel_current_turn = (
            lambda *, reason, preserve_partial_response: self.h._cancel_calls.append((reason, preserve_partial_response))
        )
        self.h._sync_voice_conversation_state = lambda: None
        self.h._tts_busy = lambda: False
        self.h._split_voice_wake_words = lambda: MainWindow._split_voice_wake_words(self.h)
        self.h._normalize_voice_text = lambda text: MainWindow._normalize_voice_text(self.h, text)
        self.h._should_dedupe_voice_text = lambda text, session_id: MainWindow._should_dedupe_voice_text(
            self.h, text, session_id
        )
        self.h._strip_wake_word = lambda text: MainWindow._strip_wake_word(self.h, text)
        self.h._is_self_echo_transcript = lambda text: MainWindow._is_self_echo_transcript(self.h, text)
        self.h._is_voice_stop_intent = lambda text: MainWindow._is_voice_stop_intent(self.h, text)
        self.h._voice_followup_open = lambda: MainWindow._voice_followup_open(self.h)
        # 상황별 규칙 명령 단계. 스텁이 아니라 실제 구현을 붙여서, 평상시(IDLE)에는
        # 일반 발화를 가로채지 않는다는 것까지 여기서 같이 지킨다.
        self.h._voice_context = lambda: MainWindow._voice_context(self.h)
        self.h._handle_voice_command = lambda text: MainWindow._handle_voice_command(self.h, text)
        self.ready: list[object] = []
        self.h._turn_dispatcher.turn_ready.connect(self.ready.append)

    def test_voice_turn_does_not_touch_keyboard_draft(self) -> None:
        MainWindow._submit_voice_turn(self.h, "크롬 열어줘", session_id=1)
        self.assertEqual(self.h._chat.current_input_text(), "보고서 작성 중")
        self.assertEqual(self.ready[0].text, "크롬 열어줘")

    def test_duplicate_stt_is_ignored(self) -> None:
        MainWindow._submit_voice_turn(self.h, "크롬 열어줘", session_id=1)
        MainWindow._submit_voice_turn(self.h, "크롬 열어줘", session_id=1)
        self.assertEqual(len(self.ready), 1)

    def test_stop_intent_requests_cancel_without_new_turn(self) -> None:
        self.h._busy = True
        MainWindow._submit_voice_turn(self.h, "잠깐", session_id=1)
        self.assertEqual(self.h._cancel_calls, [("voice_stop_intent", True)])
        self.assertEqual(len(self.ready), 0)

    def test_wake_word_off_accepts_plain_voice(self) -> None:
        MainWindow._submit_voice_turn(self.h, "오늘 날씨 알려줘", session_id=1)
        self.assertEqual(self.ready[0].text, "오늘 날씨 알려줘")

    def test_wake_word_on_requires_prefix(self) -> None:
        self.h._voice_prefs.voice_wake_word_enabled = True
        MainWindow._submit_voice_turn(self.h, "오늘 날씨 알려줘", session_id=1)
        self.assertEqual(len(self.ready), 0)
        MainWindow._submit_voice_turn(self.h, "아이리스 오늘 날씨 알려줘", session_id=1)
        self.assertEqual(self.ready[0].text, "오늘 날씨 알려줘")

    def test_followup_window_skips_wake_word_requirement(self) -> None:
        self.h._voice_prefs.voice_wake_word_enabled = True
        self.h._voice_followup_deadline = time.perf_counter() + 10
        MainWindow._submit_voice_turn(self.h, "내일은?", session_id=1)
        self.assertEqual(self.ready[0].text, "내일은?")

    def test_self_echo_transcript_is_ignored(self) -> None:
        self.h._tts_active_play = True
        self.h._last_assistant_text = "현재 서울의 날씨는 맑음입니다"
        MainWindow._submit_voice_turn(self.h, "현재 서울의 날씨는 맑음입니다", session_id=1)
        self.assertEqual(len(self.ready), 0)

    def test_barge_in_requests_cancel_and_keeps_voice_turn(self) -> None:
        self.h._busy = True
        MainWindow._submit_voice_turn(self.h, "아니 그거 말고 부산", session_id=1)
        self.assertEqual(self.h._cancel_calls, [("voice_barge_in", True)])
        self.assertEqual(self.ready[0].text, "아니 그거 말고 부산")

    def test_open_voice_followup_window_uses_preferences(self) -> None:
        self.h._voice_prefs.voice_followup_window_sec = 3
        MainWindow._open_voice_followup_window(self.h)
        self.assertGreater(self.h._voice_followup_deadline, time.perf_counter())
