"""업무 학습(로컬) — 녹화 이벤트 정리, 입력 글자 복원, 실행 보조 함수."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

import numpy as np

from iris.learning.hangul import compose
from iris.learning.local_executor import find_by_template, parse_bbox, text_matches
from iris.learning.local_learner import parse_description
from iris.learning.models import LearningEvent
from iris.learning.skill import Skill, SkillParam, apply_params, build_steps, fill, placeholders
from iris.learning.typing_capture import TypingBuffer, vk_to_char


def ev(t, kind, process="KakaoTalk.exe", title="카카오톡", **kw) -> LearningEvent:
    meta = kw.pop("metadata", {})
    return LearningEvent(timestamp=t, event_type=kind, process_name=process, window_title=title,
                         metadata=meta, **kw)


class HangulTests(TestCase):
    def test_compose(self) -> None:
        for keys, want in [("dkssud", "안녕"), ("dkssudgktpdy", "안녕하세요"), ("rkqtdl", "값이"),
                           ("dhkTek", "왔다"), ("xptmxm 123", "테스트 123"), ("dmlwk", "의자")]:
            self.assertEqual(compose(keys), want)

    def test_vk_to_char_respects_shift(self) -> None:
        self.assertEqual(vk_to_char(0x41, False), "a")
        self.assertEqual(vk_to_char(0x41, True), "A")
        self.assertEqual(vk_to_char(0x31, True), "!")
        self.assertIsNone(vk_to_char(0x0D, False))


class TypingBufferTests(TestCase):
    def _buf(self, keys: str, hangul: bool) -> TypingBuffer:
        b = TypingBuffer(hangul=hangul, started=True)
        for ch in keys:
            b.add(ch)
        return b

    def test_hangul_fallback_when_text_unreadable(self) -> None:
        typed = self._buf("dkssud", True).resolve(None, "Chrome_RenderWidgetHostHWND")
        self.assertEqual(typed.text, "안녕")

    def test_list_control_name_is_not_typed_text(self) -> None:
        """카톡 친구 목록은 WM_GETTEXT 로 'ContactListCtrl_0x…'를 돌려준다 (실제 사례)."""
        typed = self._buf("cjftn", True).resolve("ContactListCtrl_0x00010678", "EVA_VH_ListControl_Dblclk")
        self.assertEqual(typed.text, "철수")
        self.assertEqual(typed.field_text, "")

    def test_edit_control_gives_field_text(self) -> None:
        typed = self._buf("xptmxm", True).resolve("iris 테스트", "RICHEDIT50W")
        self.assertEqual(typed.text, "테스트")
        self.assertEqual(typed.field_text, "iris 테스트")

    def test_wrong_ime_guess_corrected_by_control(self) -> None:
        typed = self._buf("hello", True).resolve("hello", "Edit")
        self.assertEqual(typed.text, "hello")


class BuildStepsTests(TestCase):
    def test_kakao_demo_shape(self) -> None:
        """실제 카톡 녹화를 줄인 것 — 작업 표시줄, 지웠다 다시 친 글자, 끝난 뒤 스크롤·터미널."""
        events = [
            ev(0.0, "context", "WindowsTerminal.exe", "터미널"),
            ev(17.1, "window_change", "explorer.exe", ""),
            ev(17.2, "click", "explorer.exe", "", x=1715, y=1763, metadata={"shot": "a.jpg"}),
            ev(39.5, "window_change", metadata={"exe": "C:/kakao.exe"}),
            ev(41.30, "click", x=2039, y=492, metadata={"shot": "b.jpg"}),
            ev(41.48, "click", x=2039, y=492, metadata={"shot": "c.jpg"}),
            ev(46.4, "window_change", title="최지호"),
            ev(46.5, "click", title="최지호", x=2005, y=1445, metadata={"shot": "d.jpg"}),
            ev(49.4, "type_text", title="최지호", text="iris ㅌ"),
            ev(51.8, "click", title="카카오톡", x=1696, y=1768,
               metadata={"under": {"class": "Shell_TrayWnd"}}),
            ev(53.1, "click", title="최지호", x=1990, y=1407, metadata={"shot": "e.jpg"}),
            ev(53.7, "hotkey", title="최지호", key="backspace"),
            ev(56.6, "type_text", title="최지호", text="테스트 메시지",
               metadata={"field_text": "iris 테스트 메시지"}),
            ev(56.61, "hotkey", title="최지호", key="enter"),
            ev(58.1, "scroll", title="최지호", x=2052, y=1192, metadata={"dy": -1}),
            ev(59.8, "window_change", "WindowsTerminal.exe", "터미널"),
            ev(59.9, "click", "WindowsTerminal.exe", "터미널", x=1089, y=1196),
            ev(62.4, "type_text", "WindowsTerminal.exe", "터미널", text="끝"),
        ]
        steps = build_steps(events)
        self.assertEqual(
            [(s.kind, s.double, s.text or s.keys) for s in steps],
            [
                ("activate_app", False, ""),
                ("click", True, ""),
                ("click", False, ""),
                ("type", False, "iris 테스트 메시지"),
                ("hotkey", False, "enter"),
            ],
        )
        self.assertEqual(steps[0].exe, "C:/kakao.exe")
        self.assertTrue(steps[3].clear_first)


class ParamTests(TestCase):
    def _skill(self) -> Skill:
        from iris.learning.skill import SkillStep

        return Skill(
            skill_id="s",
            steps=[
                SkillStep(kind="type", text="철수"),
                SkillStep(kind="click", target="'철수' 대화방", visible_text="철수"),
                SkillStep(kind="type", text="안녕"),
            ],
        )

    def test_apply_and_fill(self) -> None:
        sk = self._skill()
        apply_params(sk, [SkillParam("recipient", "받는 사람", "철수"), SkillParam("message", "메시지", "안녕")])
        self.assertEqual(sk.steps[0].text, "{recipient}")
        self.assertEqual(sk.steps[1].target, "'{recipient}' 대화방")
        self.assertEqual(placeholders(sk.steps[1].target), ["recipient"])
        self.assertEqual(fill(sk.steps[2].text, {"message": "늦어"}), "늦어")

    def test_rename_and_remove_params(self) -> None:
        sk = self._skill()
        apply_params(sk, [SkillParam("text", "입력", "안녕"), SkillParam("text2", "x", "철수")])
        apply_params(sk, [SkillParam("message", "메시지", "안녕")])
        self.assertEqual(sk.steps[2].text, "{message}")
        self.assertEqual(sk.steps[0].text, "철수")  # 칸에서 빼면 녹화 값으로 돌아간다

    def test_round_trip(self) -> None:
        sk = self._skill()
        apply_params(sk, [SkillParam("message", "메시지", "안녕")])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "skill.json"
            sk.save(path)
            back = Skill.load(path)
        self.assertEqual(back.params[0].name, "message")
        self.assertEqual(back.steps[2].text, "{message}")


class HelperTests(TestCase):
    def test_parse_description(self) -> None:
        self.assertEqual(parse_description("요소: 메시지 입력 / 글자: 메시지 입력"), ("메시지 입력", "메시지 입력"))
        self.assertEqual(parse_description("요소: 최지호\n/ 글자: 최지호")[1], "최지호")

    def test_parse_bbox(self) -> None:
        self.assertEqual(parse_bbox('```json {"bbox_2d": [40, 39, 405, 87]} ```'), (40.0, 39.0, 405.0, 87.0))
        self.assertIsNone(parse_bbox("못 찾음"))

    def test_text_matches(self) -> None:
        self.assertTrue(text_matches("최지호", "'최지호' (나)"))
        self.assertFalse(text_matches("최지호", "박지원"))
        self.assertFalse(text_matches("", "아무거나"))

    def test_template_finds_moved_patch(self) -> None:
        rng = np.random.default_rng(0)
        shot = rng.integers(0, 255, (600, 900, 3), dtype=np.uint8)
        screen = np.zeros_like(shot)
        screen[50:550, 100:900] = shot[0:500, 0:800]  # 창이 오른쪽·아래로 옮겨짐
        spot = find_by_template(screen, shot, 300, 200)
        self.assertIsNotNone(spot)
        self.assertAlmostEqual(spot.x, 400, delta=1)
        self.assertAlmostEqual(spot.y, 250, delta=1)

    def test_template_rejects_absent_patch(self) -> None:
        rng = np.random.default_rng(1)
        shot = rng.integers(0, 255, (400, 400, 3), dtype=np.uint8)
        screen = rng.integers(0, 255, (400, 400, 3), dtype=np.uint8)
        self.assertIsNone(find_by_template(screen, shot, 200, 200))


class SkillRouterTests(TestCase):
    def setUp(self) -> None:
        from iris.learning.skill_router import SkillInfo

        self.skills = [
            SkillInfo(1, "나와의 채팅에 카톡 보내기", "", "KakaoTalk.exe", [("text", "보낼 메시지", "x")]),
            SkillInfo(3, "엑셀 보고서 열기", "", "EXCEL.EXE", []),
        ]

    def match(self, text: str):
        from iris.learning.skill_router import match_skill

        return match_skill(text, self.skills)

    def test_quoted_value(self) -> None:
        m = self.match('나와의 채팅에 "안녕 IRIS"라고 보내줘')
        self.assertEqual((m.workflow_id, m.params), (1, {"text": "안녕 IRIS"}))

    def test_rago_value_without_quotes(self) -> None:
        m = self.match("나와의 채팅에 안녕이라고 카톡 보내줘")
        self.assertEqual(m.params, {"text": "안녕"})

    def test_missing_value_is_reported(self) -> None:
        m = self.match("카톡 보내줘")
        self.assertEqual(m.workflow_id, 1)
        self.assertEqual(m.missing, ["text"])

    def test_unrelated_or_no_request(self) -> None:
        self.assertIsNone(self.match("오늘 날씨 어때?"))
        self.assertIsNone(self.match("나와의 채팅에 카톡 보내기 스킬은 뭐야"))

    def test_picks_the_closer_skill(self) -> None:
        self.assertEqual(self.match("엑셀 보고서 열어줘").workflow_id, 3)


class WindowOffsetTests(TestCase):
    def test_input_box_follows_moved_and_resized_window(self) -> None:
        from unittest import mock

        from iris.learning import local_executor as ex
        from iris.learning.skill import SkillStep

        # 녹화: 창 (1000,100)-(1400,900), 입력창은 아래쪽 (1200, 850)
        step = SkillStep(kind="click", process="KakaoTalk.exe", title="최지호",
                         x=1200, y=850, win_rect=[1000, 100, 1400, 900])
        with mock.patch.object(ex, "_process_windows", return_value=[(7, "최지호")]), \
                mock.patch.object(ex, "window_rect", return_value=(500, 200, 900, 1100)):
            spot = ex.find_by_window_offset(step)
        # 창이 왼쪽으로 옮겨지고 아래로 100 늘어남 — 아래쪽 입력창은 아래 가장자리 기준
        self.assertEqual((spot.x, spot.y), (700.0, 1050.0))

    def test_no_window_no_guess(self) -> None:
        from unittest import mock

        from iris.learning import local_executor as ex
        from iris.learning.skill import SkillStep

        step = SkillStep(kind="click", process="KakaoTalk.exe", title="최지호",
                         x=1200, y=850, win_rect=[1000, 100, 1400, 900])
        with mock.patch.object(ex, "_process_windows", return_value=[(7, "다른 방")]):
            self.assertIsNone(ex.find_by_window_offset(step))


class FieldTypingTests(TestCase):
    def _run(self, parts: list[str], hangul: bool = False) -> str:
        b = TypingBuffer(hangul=hangul, started=True)
        for i, part in enumerate(parts):
            if i:
                b.toggle_hangul()
            for ch in part:
                b.add(ch)
        return b.resolve(None, "RICHEDIT50W").text

    def test_kakao_reports_english_mode_but_text_is_korean(self) -> None:
        self.assertEqual(self._run(["enqjsWo shrghk"]), "두번째 녹화")

    def test_english_stays_english(self) -> None:
        self.assertEqual(self._run(["hello world"]), "hello world")
        self.assertEqual(self._run(["meeting at 3"]), "meeting at 3")

    def test_hangul_english_toggle_segments(self) -> None:
        self.assertEqual(self._run(["IRIS ", "xptmxm"]), "IRIS 테스트")
        self.assertEqual(self._run(["dlqfurckd ", "test"]), "입력창 test")

    def test_placeholder_text_does_not_replace_typed_text(self) -> None:
        b = TypingBuffer(started=True)
        for ch in "dkssud":
            b.add(ch)
        self.assertEqual(b.resolve("메시지 입력", "RICHEDIT50W").text, "안녕")


class TypeAfterClickTests(TestCase):
    def test_type_after_clicking_field_clears_it_and_idle_focus_is_dropped(self) -> None:
        events = [
            ev(0.0, "context", "python.exe", "IRIS"),
            ev(1.0, "window_change", metadata={"exe": "k.exe"}),
            ev(2.0, "click", title="최지호", x=10, y=10),
            ev(3.0, "type_text", title="최지호", text="안녕"),
            ev(3.1, "hotkey", title="최지호", key="enter"),
            # 녹화를 끄러 IRIS 로 돌아가는 순간 포커스가 비었다
            ev(5.0, "window_change", "", ""),
            ev(5.1, "click", "", "", x=1301, y=889),
        ]
        steps = build_steps(events)
        self.assertEqual([s.kind for s in steps], ["activate_app", "click", "type", "hotkey"])
        self.assertTrue(steps[2].clear_first)
