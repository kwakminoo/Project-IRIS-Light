"""코드 리뷰에서 나온 버그 — 비밀번호 키 유출, Shift 빠짐, 재생 실패, 채팅 가로채기 등."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from iris.learning import recorder as rec_mod
from iris.learning.skill import Skill, SkillParam, SkillStep, apply_params


def _recorder(store_key_chars: bool = True):
    tmp = Path(tempfile.mkdtemp())
    with mock.patch.object(rec_mod, "session_dir", return_value=tmp):
        r = rec_mod.DemonstrationRecorder("t", store_key_chars=store_key_chars)
    r._last_fg = ("KakaoTalk.exe", "카카오톡", 1)
    return r


class _Env:
    """훅·Win32 없이 키 이벤트를 흘려 넣는다."""

    def __init__(self, r, pwd: bool = False) -> None:
        self.r = r
        self.pwd = pwd

    def __enter__(self):
        r = self.r
        self._patches = [
            mock.patch.object(rec_mod, "_is_password_control", side_effect=lambda: self.pwd),
            mock.patch.object(r, "_maybe_window_change", return_value=("KakaoTalk.exe", "카카오톡")),
            mock.patch.object(rec_mod, "focused_control", return_value=0),
            mock.patch.object(rec_mod, "ime_hangul_mode", return_value=False),
            mock.patch.object(rec_mod, "read_control_text", return_value=None),
            mock.patch.object(rec_mod, "control_class", return_value=""),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()

    def key(self, vk: int, name: str | None = None) -> None:
        self.r._handle_key("key_down", name, vk)
        self.r._handle_key("key_up", name, vk)


class RecorderPrivacyTests(TestCase):
    def test_password_keys_keep_no_vk(self) -> None:
        r = _recorder()
        with _Env(r, pwd=True) as env:
            env.key(0x41, "a")
        keys = [e for e in r._events if e.event_type in ("key_down", "key_up")]
        self.assertTrue(keys)
        for e in keys:
            self.assertEqual(e.key, "[REDACTED]")
            self.assertEqual(e.metadata["vk"], 0)

    def test_password_typed_then_alt_tab_stays_redacted(self) -> None:
        r = _recorder()
        with _Env(r, pwd=True) as env:
            for vk, ch in ((0x50, "p"), (0x57, "w")):
                env.key(vk, ch)
            env.pwd = False  # Alt+Tab 으로 다른 창에 포커스가 간 뒤 정리된다
            r._flush_typing("window_change")
        typed = [e for e in r._events if e.event_type == "type_text"]
        self.assertEqual(len(typed), 1)
        self.assertEqual(typed[0].text, "[REDACTED]")
        self.assertEqual(typed[0].metadata["raw_keys"], "")
        self.assertEqual(typed[0].metadata["field_text"], "")

    def test_no_key_chars_policy_keeps_no_raw_keys(self) -> None:
        r = _recorder(store_key_chars=False)
        with _Env(r) as env:
            env.key(0x48, "h")
            env.key(0x49, "i")
            r._flush_typing("key")
        typed = [e for e in r._events if e.event_type == "type_text"][0]
        self.assertEqual(typed.text, "[REDACTED]")
        self.assertEqual(typed.metadata["raw_keys"], "")
        for e in r._events:
            if e.event_type in ("key_down", "key_up"):
                self.assertEqual(e.metadata["vk"], 0)

    def test_shift_enter_keeps_shift(self) -> None:
        r = _recorder()
        with _Env(r) as env:
            r._handle_key("key_down", "shift", 0xA0)
            env.key(0x0D, "enter")
            r._handle_key("key_up", "shift", 0xA0)
            env.key(0x0D, "enter")
        hot = [e.key for e in r._events if e.event_type == "hotkey"]
        self.assertEqual(hot, ["shift+enter", "enter"])


class ReplayTests(TestCase):
    def test_unknown_vk_names_replay(self) -> None:
        from pynput.keyboard import KeyCode

        from iris.learning.local_executor import _pynput_key

        self.assertEqual(_pynput_key("vk14"), KeyCode.from_vk(0x14))
        with self.assertRaises(ValueError):
            _pynput_key("nonsense")

    def test_legacy_workflow_fails_with_clear_message(self) -> None:
        from iris.learning.local_executor import LocalSkillExecutor

        ex = LocalSkillExecutor(mock.MagicMock(), ollama_base_url="http://fake")
        run = ex.execute(trace_id="old", task="예전 업무")
        self.assertEqual(run.status, "failed")
        self.assertIn("다시 배울게요", run.message)


class ReviewDialogTests(TestCase):
    def test_param_inside_longer_text_is_kept(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        from iris.ui.learning.skill_review_dialog import SkillReviewDialog

        app = QApplication.instance() or QApplication([])
        skill = Skill(
            skill_id="s",
            steps=[SkillStep(kind="type", text="안녕 IRIS 내일 봐")],
        )
        apply_params(skill, [SkillParam(name="when", label="언제", example="내일")])
        self.assertEqual(skill.steps[0].text, "안녕 IRIS {when} 봐")

        dlg = SkillReviewDialog(skill)
        params = dlg.result_params()
        self.assertEqual([(p.name, p.example) for p in params], [("when", "내일")])
        del app


class PinnedStatusQuestionTests(TestCase):
    def test_status_questions_only(self) -> None:
        from iris.ui.window.main_window import is_pinned_status_question as ask

        for t in ("고정한 창 어때?", "지금 고정중인 어때", "감시 중인 창 상태 알려줘", "📌 창 에러 났어?"):
            self.assertTrue(ask(t), t)
        for t in (
            "고정한 창 해제해줘",
            "모니터링 화면 열어줘",
            "감시 창 닫아줘",
            "핀터레스트 화면 열어줘",
            "이 창 고정해줘",
            "오늘 날씨 어때",
        ):
            self.assertFalse(ask(t), t)


class HermesRangeTests(TestCase):
    def _range(self, requires: str, floor: str = ""):
        from iris.system import hermes_install as hi

        d = Path(tempfile.mkdtemp())
        (d / "pyproject.toml").write_text(f'[project]\nrequires-python = "{requires}"\n', encoding="utf-8")
        if floor:
            (d / "uv.lock").write_text(
                f"supported-markers = [\n  \"python_full_version >= '{floor}'\",\n]\n",
                encoding="utf-8",
            )
        return hi.hermes_python_range(d)

    def test_lock_floor_above_default_ceiling_is_not_empty(self) -> None:
        self.assertEqual(self._range(">=3.11", "3.14"), ((3, 14), (3, 15)))

    def test_major_only_ceiling(self) -> None:
        self.assertEqual(self._range(">=3.11,<4", "3.14"), ((3, 14), (4, 0)))
