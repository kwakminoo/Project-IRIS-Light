"""전화·알림 음성 — 규칙 인텐트, adb 상태 파싱, 낭독 문안, 사이드바 힌트."""

from __future__ import annotations

import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from iris.audio.alert_speech import (
    MAX_ALERT_CHARS,
    AlertPriority,
    call_announcement,
    notification_announcement,
)
from iris.runtime.voice_intents import (
    IntentContext,
    VoiceIntent,
    allowed_intents,
    match_intent,
    normalize,
    prompts_for,
    similarity,
)
from iris.system.phone_control import (
    CallSnapshot,
    CallState,
    _command_succeeded,
    _parse_registry,
    _parse_telecom,
)

# 전화가 울리는 중에 나올 수 있는, 통화 조작과 무관한 말들.
# 되돌릴 수 없는 동작(받기/끊기)이 여기에 걸리면 안 된다.
_UNRELATED = (
    "오늘 날씨 어때",
    "회의록 정리해줘",
    "이 파일 열어줘",
    "노래 틀어줘",
    "밥 먹었어",
    "조금만 기다려",
    "화면 캡처해줘",
    "메일 확인해줘",
    "자료 찾아줘",
    "바다 보고 싶다",
    "바다가 예쁘네",
    "다 줘",
    "줘 봐",
    "받침이 뭐야",
    "전화번호 알려줘",
    "전화기 어디 있어",
    "통화 기록 보여줘",
    "내일 일정 알려줘",
    "그만 좀 해",
    "다시 해줘",
    "다시 시작해줘",
    "읽어줘 이 문서",
)

_DESTRUCTIVE = (VoiceIntent.ANSWER_CALL, VoiceIntent.REJECT_CALL, VoiceIntent.HANG_UP)


class IntentMatchTests(TestCase):
    def test_answers_call_on_plain_phrase(self) -> None:
        for text in ("전화 받아줘", "전화받아", "받아줘", "전화 좀 받아줘", "연결해줘"):
            with self.subTest(text=text):
                found = match_intent(text, context=IntentContext.CALL_RINGING)
                self.assertIsNotNone(found)
                assert found is not None
                self.assertIs(found.intent, VoiceIntent.ANSWER_CALL)

    def test_tolerates_slurred_pronunciation(self) -> None:
        """이 기능이 존재하는 이유 — 발음이 흐려도 걸려야 한다."""
        for text in ("바다줘", "반아줘", "전화 바다줘", "전하 바다주세요"):
            with self.subTest(text=text):
                found = match_intent(text, context=IntentContext.CALL_RINGING)
                self.assertIsNotNone(found, f"{text!r} 를 놓쳤다")
                assert found is not None
                self.assertIs(found.intent, VoiceIntent.ANSWER_CALL)

    def test_leading_filler_and_wake_word_ignored(self) -> None:
        found = match_intent("아이리스 어 그래 전화 받아줘", context=IntentContext.CALL_RINGING)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertIs(found.intent, VoiceIntent.ANSWER_CALL)

    def test_negation_flips_to_reject(self) -> None:
        for text in ("전화 받지마", "거절해줘", "끊어줘", "안 받을래"):
            with self.subTest(text=text):
                found = match_intent(text, context=IntentContext.CALL_RINGING)
                self.assertIsNotNone(found)
                assert found is not None
                self.assertIs(found.intent, VoiceIntent.REJECT_CALL)

    def test_context_gates_call_intents(self) -> None:
        """전화가 안 울리는데 '받아줘'라고 해서 뭔가 받아지면 안 된다."""
        for text in ("전화 받아줘", "받아줘", "거절해줘"):
            with self.subTest(text=text):
                self.assertIsNone(match_intent(text, context=IntentContext.IDLE))

    def test_no_destructive_false_positives(self) -> None:
        for context in IntentContext:
            for text in _UNRELATED:
                found = match_intent(text, context=context)
                if found is not None and found.intent in _DESTRUCTIVE:
                    self.fail(
                        f"{text!r} 가 [{context.value}] 에서 {found.intent.value} 로 잡혔다 "
                        f"(phrase={found.matched_phrase!r} conf={found.confidence})"
                    )

    def test_idle_never_intercepts_normal_speech(self) -> None:
        """평상시에는 규칙이 일반 요청을 가로채면 안 된다."""
        for text in _UNRELATED:
            with self.subTest(text=text):
                self.assertIsNone(match_intent(text, context=IntentContext.IDLE))

    def test_hang_up_only_during_call(self) -> None:
        self.assertIsNone(match_intent("통화 종료해줘", context=IntentContext.IDLE))
        found = match_intent("통화 종료해줘", context=IntentContext.CALL_ACTIVE)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertIs(found.intent, VoiceIntent.HANG_UP)

    def test_alert_intents_need_a_pending_alert(self) -> None:
        self.assertIsNone(match_intent("다시 말해줘", context=IntentContext.IDLE))
        found = match_intent("다시 말해줘", context=IntentContext.ALERT_PENDING)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertIs(found.intent, VoiceIntent.REPEAT_ALERT)

    def test_empty_and_noise(self) -> None:
        for text in ("", "   ", "...", "음", "어"):
            with self.subTest(text=text):
                self.assertIsNone(match_intent(text, context=IntentContext.CALL_RINGING))

    def test_normalize_strips_wake_word_and_spacing(self) -> None:
        self.assertEqual(normalize("아이리스, 전화 받아줘!"), "전화받아줘")

    def test_similarity_separates_related_from_unrelated(self) -> None:
        self.assertGreater(similarity("바다줘", "받아줘"), 0.7)
        self.assertLess(similarity("오늘날씨어때", "받아줘"), 0.4)


class IntentContextExposureTests(TestCase):
    def test_prompts_track_context(self) -> None:
        self.assertIn("전화 받아줘", prompts_for(IntentContext.CALL_RINGING))
        self.assertNotIn("전화 받아줘", prompts_for(IntentContext.IDLE))
        self.assertEqual(prompts_for(IntentContext.IDLE), ())

    def test_allowed_intents_match_prompts(self) -> None:
        for context in IntentContext:
            self.assertEqual(len(allowed_intents(context)), len(prompts_for(context)))


class CallStateParsingTests(TestCase):
    def test_registry_states(self) -> None:
        for code, expected in (
            ("0", CallState.IDLE),
            ("1", CallState.RINGING),
            ("2", CallState.ACTIVE),
        ):
            with self.subTest(code=code):
                state, _num = _parse_registry(f"  mCallState={code}\n")
                self.assertIs(state, expected)

    def test_registry_tolerates_spacing(self) -> None:
        state, _num = _parse_registry("mCallState = 1")
        self.assertIs(state, CallState.RINGING)

    def test_registry_reads_incoming_number(self) -> None:
        _state, number = _parse_registry("mCallState=1\nmCallIncomingNumber=+821012345678")
        self.assertEqual(number, "+821012345678")

    def test_registry_unknown_when_absent(self) -> None:
        state, number = _parse_registry("아무 관계 없는 덤프")
        self.assertIs(state, CallState.UNKNOWN)
        self.assertEqual(number, "")

    def test_telecom_fallback(self) -> None:
        self.assertIs(_parse_telecom("Call id=1 state=RINGING"), CallState.RINGING)
        self.assertIs(_parse_telecom("Call id=1 state=ACTIVE"), CallState.ACTIVE)
        self.assertIs(_parse_telecom(""), CallState.UNKNOWN)

    def test_snapshot_display_name_priority(self) -> None:
        self.assertEqual(
            CallSnapshot(caller="홍길동", number="01012345678").display_name, "홍길동"
        )
        self.assertEqual(CallSnapshot(number="01012345678").display_name, "01012345678")
        self.assertEqual(CallSnapshot().display_name, "알 수 없는 번호")

    def test_ringing_flag(self) -> None:
        self.assertTrue(CallSnapshot(state=CallState.RINGING).ringing)
        self.assertFalse(CallSnapshot(state=CallState.ACTIVE).ringing)


class AdbCommandSuccessTests(TestCase):
    """`cmd telecom` 은 구현이 없어도 종료 코드 0 을 준다.

    Android 33 에뮬레이터에서 실측한 내용이다. accept-ringing-call 이 통째로
    없는데도 rc=0 + "No shell command implementation." 만 나온다. 종료 코드만
    믿으면 폴백이 영영 안 걸리고, 전화를 못 받았는데 받았다고 보고하게 된다.
    """

    def test_unimplemented_command_is_not_success(self) -> None:
        self.assertFalse(_command_succeeded(0, "No shell command implementation.", ""))

    def test_unimplemented_on_stderr_too(self) -> None:
        self.assertFalse(_command_succeeded(0, "", "No shell command implementation."))

    def test_unknown_command_is_not_success(self) -> None:
        self.assertFalse(_command_succeeded(0, "Unknown command: foo", ""))
        self.assertFalse(_command_succeeded(0, "usage: telecom [subcommand]", ""))

    def test_case_insensitive(self) -> None:
        self.assertFalse(_command_succeeded(0, "NO SHELL COMMAND IMPLEMENTATION", ""))

    def test_silent_success_is_success(self) -> None:
        """input keyevent 는 성공하면 아무것도 출력하지 않는다."""
        self.assertTrue(_command_succeeded(0, "", ""))

    def test_nonzero_exit_is_failure(self) -> None:
        self.assertFalse(_command_succeeded(1, "", ""))


class AnnouncementTests(TestCase):
    def test_uses_caller_name_when_known(self) -> None:
        self.assertIn("홍길동", call_announcement("홍길동", number="01012345678"))

    def test_reads_only_last_four_digits(self) -> None:
        text = call_announcement("01012345678", number="01012345678")
        self.assertIn("5678", text)
        self.assertNotIn("01012345678", text)

    def test_unknown_caller(self) -> None:
        self.assertIn("전화가 왔습니다", call_announcement("", number=""))

    def test_notification_joins_title_and_body(self) -> None:
        self.assertEqual(notification_announcement("빌드 실패", "3 errors"), "빌드 실패. 3 errors")
        self.assertEqual(notification_announcement("빌드 실패", "빌드 실패"), "빌드 실패")
        self.assertEqual(notification_announcement("", ""), "새 알림이 있습니다.")

    def test_call_beats_notice_priority(self) -> None:
        self.assertGreater(AlertPriority.CALL, AlertPriority.NOTICE)

    def test_alert_length_cap_is_sane(self) -> None:
        """길면 상황이 끝난 뒤까지 떠든다."""
        self.assertLessEqual(MAX_ALERT_CHARS, 200)


class VoiceHintPanelTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def _panel(self):
        from iris.ui.sidebar.voice_hint_panel import VoiceHintPanel

        return VoiceHintPanel()

    def _prompt_texts(self, panel) -> list[str]:
        from PyQt6.QtWidgets import QPushButton

        return [b.text() for b in panel.findChildren(QPushButton)]

    def test_hidden_when_idle(self) -> None:
        panel = self._panel()
        panel.set_context(IntentContext.IDLE)
        self.assertTrue(panel.isHidden())
        self.assertEqual(self._prompt_texts(panel), [])

    def test_shows_answer_prompt_while_ringing(self) -> None:
        panel = self._panel()
        panel.set_context(IntentContext.CALL_RINGING, caption="수신 전화 · 홍길동")
        self.assertFalse(panel.isHidden())
        self.assertIn('"전화 받아줘"', self._prompt_texts(panel))

    def test_rebuild_does_not_accumulate(self) -> None:
        """deleteLater 만으로는 이전 상황의 문장이 남는다."""
        panel = self._panel()
        panel.set_context(IntentContext.CALL_RINGING)
        panel.set_context(IntentContext.CALL_ACTIVE)
        self.assertEqual(self._prompt_texts(panel), ['"통화 종료해줘"'])

    def test_click_emits_intent(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        panel = self._panel()
        panel.set_context(IntentContext.CALL_RINGING)
        seen: list[str] = []
        panel.prompt_activated.connect(seen.append)
        panel.findChildren(QPushButton)[0].click()
        self.assertEqual(seen, [VoiceIntent.ANSWER_CALL.value])

    def test_prompt_buttons_declare_padding(self) -> None:
        """테마의 QPushButton { padding: 6px 12px } 가 좁은 사이드바에서 글자를 자른다."""
        from PyQt6.QtWidgets import QPushButton

        panel = self._panel()
        panel.set_context(IntentContext.CALL_RINGING)
        for btn in panel.findChildren(QPushButton):
            self.assertIn("padding", btn.styleSheet())

    def test_pref_toggle_hides_panel(self) -> None:
        panel = self._panel()
        panel.set_context(IntentContext.CALL_RINGING)
        panel.set_enabled_by_pref(False)
        self.assertTrue(panel.isHidden())
