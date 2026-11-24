"""위키 IRIS 칸 — 상태 스냅샷, 예약 루틴 등록·실행·기록."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from iris.knowledge.iris_state import (
    IRIS_DIR,
    build_state,
    diff_state,
    is_secret_label,
    remove_routine_note,
    render_index,
    render_routine_note,
    sync_iris_index,
    sync_routine_note,
)
from iris.knowledge.iris_wiki import IrisWiki
from iris.runtime.routine_runner import (
    build_run_messages,
    collect_due,
    format_delivery,
    notify_summary,
    record_missed,
    record_result,
)
from iris.runtime.routine_schedule import (
    Schedule,
    check_due,
    parse_time_of_day,
    parse_weekdays,
)
from iris.storage.database import Database
from iris.storage.routines import (
    STATUS_FAILED,
    STATUS_MISSED,
    STATUS_OK,
    create_routine,
    delete_routine,
    find_routine_by_name,
    list_routines,
    normalize_deliver,
    update_routine,
)


class _History:
    enabled = True
    record_chat = True
    record_actions = True
    record_artifacts = False
    record_inputs = True


class _Failover:
    enabled = True
    mode = "model-chain"
    preempt_enabled = True
    preempt_percent = 95.0
    chain = [SimpleNamespace(model="free:a", backend="ollama")]


class _Provider:
    name = "OpenRouter"
    api_key = "sk-must-never-appear"
    enabled = True


class IrisStateSecretTests(TestCase):
    """키는 bool 로만 — 위키는 평문 마크다운이다."""

    def setUp(self) -> None:
        self.state = build_state(
            ollama_model="qwen3:8b",
            hermes_enabled=True,
            agent_base_url="http://127.0.0.1:8642/v1",
            hermes_api_key="sk-hermes-must-never-appear",
            api_providers=[_Provider()],
            history=_History(),
            failover=_Failover(),
            embed_model="bge-m3",
        )

    def test_no_secret_value_survives_anywhere(self) -> None:
        blob = render_index(self.state, [])
        self.assertNotIn("sk-hermes-must-never-appear", blob)
        self.assertNotIn("sk-must-never-appear", blob)
        self.assertIn("설정됨", blob)

    def test_absent_key_says_so_plainly(self) -> None:
        state = build_state(hermes_enabled=True, hermes_api_key="")
        self.assertEqual(state["Iris Agent API 키"], "없음")

    def test_secret_label_detection(self) -> None:
        self.assertTrue(is_secret_label("Hermes API 키"))
        self.assertTrue(is_secret_label("access token"))
        self.assertFalse(is_secret_label("대화 모델"))

    def test_state_covers_what_the_user_configured(self) -> None:
        self.assertEqual(self.state["대화 모델"], "qwen3:8b")
        self.assertEqual(self.state["백엔드"], "Iris Agent")
        self.assertIn("대화", self.state["History 기록"])
        self.assertIn("bge-m3", self.state["History 검색"])
        self.assertIn("free:a", self.state["전환 후보"])

    def test_diff_reports_only_what_changed(self) -> None:
        after = {**self.state, "대화 모델": "gemma4:free"}
        self.assertEqual(diff_state(self.state, after), ["대화 모델: qwen3:8b → gemma4:free"])
        self.assertEqual(diff_state(self.state, self.state), [])


class RoutineLifecycleTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "r.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        self.base = datetime(2026, 9, 29, 8, 0)  # 화요일 08:00
        self.news = create_routine(
            self.db,
            name="아침 뉴스 브리핑",
            task="오늘 주요 뉴스 3개를 골라 한 줄씩 정리해줘",
            time_of_day="09:00",
            now=self.base,
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_the_users_sentence_is_stored_verbatim(self) -> None:
        """할 일을 미리 요약하면 '3개', '한 줄씩' 같은 조건을 잃는다."""
        self.assertEqual(
            self.news.task, "오늘 주요 뉴스 3개를 골라 한 줄씩 정리해줘"
        )
        msgs = build_run_messages(self.news)
        self.assertEqual(msgs[-1]["content"], self.news.task)

    def test_default_delivery_is_chat_and_notify(self) -> None:
        self.assertEqual(self.news.deliver, "chat,notify")
        self.assertTrue(self.news.wants("chat") and self.news.wants("notify"))
        self.assertFalse(self.news.wants("voice"))

    def test_delivery_can_be_changed_later(self) -> None:
        changed = update_routine(self.db, self.news.id, deliver="음성,위키")
        self.assertEqual(changed.deliver, "voice,wiki")
        self.assertFalse(changed.wants("chat"))
        back = update_routine(self.db, self.news.id, deliver="채팅")
        self.assertTrue(back.wants("chat"))

    def test_first_run_is_today_when_the_hour_has_not_passed(self) -> None:
        self.assertEqual(self.news.next_run_at, "2026-09-29T09:00:00")

    def test_changing_the_schedule_moves_the_next_run(self) -> None:
        weekly = update_routine(self.db, self.news.id, kind="weekly", weekdays="mon,fri")
        self.assertEqual(weekly.kind, "weekly")
        self.assertNotEqual(weekly.next_run_at, self.news.next_run_at)

    def test_pausing_keeps_the_routine_but_stops_it_running(self) -> None:
        update_routine(self.db, self.news.id, enabled=False)
        run_now, missed = collect_due(self.db, datetime(2026, 9, 29, 9, 0))
        self.assertEqual((run_now, missed), ([], []))
        self.assertEqual(len(list_routines(self.db)), 1)

    def test_lookup_by_name_so_the_model_can_say_that_routine(self) -> None:
        found = find_routine_by_name(self.db, "아침 뉴스 브리핑")
        self.assertEqual(found.id, self.news.id)
        self.assertIsNone(find_routine_by_name(self.db, "없는 것"))


class RoutineExecutionTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "r.db")
        self.base = datetime(2026, 9, 29, 8, 0)
        self.r = create_routine(
            self.db, name="아침 뉴스", task="뉴스 3개", time_of_day="09:00", now=self.base
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_runs_at_the_scheduled_minute(self) -> None:
        run_now, _ = collect_due(self.db, datetime(2026, 9, 29, 9, 0))
        self.assertEqual(len(run_now), 1)
        self.assertEqual(run_now[0].check.note(), "")

    def test_short_delay_still_runs_but_says_it_was_late(self) -> None:
        run_now, _ = collect_due(self.db, datetime(2026, 9, 29, 10, 30))
        self.assertTrue(run_now)
        self.assertIn("90분 늦게", run_now[0].check.note())

    def test_app_was_off_too_long_so_the_run_is_skipped_not_backfilled(self) -> None:
        """새벽에 꺼뒀다 저녁에 켰다고 아침 브리핑이 쏟아지면 안 된다."""
        run_now, missed = collect_due(self.db, datetime(2026, 9, 29, 20, 0))
        self.assertEqual(run_now, [])
        self.assertEqual(len(missed), 1)

        after = record_missed(self.db, missed[0], datetime(2026, 9, 29, 20, 0))
        self.assertEqual(after.run_count, 0)
        self.assertEqual(after.miss_count, 1)
        self.assertEqual(after.last_status, STATUS_MISSED)
        self.assertEqual(after.next_run_at, "2026-09-30T09:00:00")
        self.assertIn("건너뛰었습니다", after.last_result)

    def test_success_records_result_and_reschedules(self) -> None:
        run_now, _ = collect_due(self.db, datetime(2026, 9, 29, 9, 0))
        done = record_result(
            self.db, run_now[0], text="1. A\n2. B\n3. C", now=datetime(2026, 9, 29, 9, 0)
        )
        self.assertEqual(done.last_status, STATUS_OK)
        self.assertEqual(done.run_count, 1)
        self.assertEqual(done.next_run_at, "2026-09-30T09:00:00")

    def test_failure_is_recorded_without_losing_the_schedule(self) -> None:
        run_now, _ = collect_due(self.db, datetime(2026, 9, 29, 9, 0))
        failed = record_result(
            self.db, run_now[0], error="검색 한도 초과", now=datetime(2026, 9, 29, 9, 0)
        )
        self.assertEqual(failed.last_status, STATUS_FAILED)
        self.assertIn("한도 초과", failed.last_result)
        self.assertEqual(failed.next_run_at, "2026-09-30T09:00:00")

    def test_one_shot_routine_stops_after_running(self) -> None:
        once = create_routine(
            self.db, name="한 번만", task="한 번", kind="once",
            at="2026-10-05T07:00:00", now=self.base,
        )
        run_now, _ = collect_due(self.db, datetime(2026, 10, 5, 7, 0), limit=9)
        target = [d for d in run_now if d.routine.id == once.id]
        self.assertTrue(target)
        after = record_result(
            self.db, target[0], text="끝", now=datetime(2026, 10, 5, 7, 0)
        )
        self.assertEqual(after.next_run_at, "")

    def test_a_tick_does_not_run_everything_at_once(self) -> None:
        for i in range(5):
            create_routine(
                self.db, name=f"기타{i}", task="뭔가", time_of_day="09:00", now=self.base
            )
        run_now, _ = collect_due(self.db, datetime(2026, 9, 29, 9, 0))
        self.assertLessEqual(len(run_now), 2)

    def test_run_prompt_tells_the_model_not_to_ask_back(self) -> None:
        msgs = build_run_messages(self.r)
        self.assertIn("되묻지 말고", msgs[0]["content"])
        self.assertIn("지어내지 말고", msgs[0]["content"])

    def test_delivery_text_surfaces_lateness(self) -> None:
        on_time = check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 9, 0))
        self.assertEqual(format_delivery(self.r, "본문", on_time), "**아침 뉴스**\n\n본문")
        late = check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 9, 30))
        self.assertIn("30분 늦게", format_delivery(self.r, "본문", late))

    def test_notify_summary_fits_a_popup(self) -> None:
        self.assertEqual(len(notify_summary(self.r, "가" * 500)), 120)
        self.assertEqual(notify_summary(self.r, ""), "결과 없음")


class IrisWikiSectionTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "r.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        self.state = build_state(ollama_model="qwen3:8b", history=_History())
        self.r = create_routine(
            self.db,
            name="아침 뉴스 브리핑",
            task="뉴스 3개 정리",
            time_of_day="09:00",
            now=datetime(2026, 9, 29, 8, 0),
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_iris_folder_exists_from_the_start(self) -> None:
        self.assertTrue((self.wiki.user_root / IRIS_DIR).is_dir())
        self.assertTrue((self.wiki.user_root / IRIS_DIR / "routines").is_dir())

    def test_index_lists_state_and_routines(self) -> None:
        sync_iris_index(self.wiki, self.state, [self.r])
        text = (self.wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        self.assertIn("# IRIS", text)
        self.assertIn("qwen3:8b", text)
        self.assertIn("아침 뉴스 브리핑", text)
        self.assertIn("매일 09:00", text)
        self.assertIn("채팅 · 알림", text)

    def test_index_shows_a_readable_name_not_a_slug(self) -> None:
        sync_iris_index(self.wiki, self.state, [self.r])
        text = (self.wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        self.assertIn("[[아침-뉴스-브리핑|아침 뉴스 브리핑]]", text)

    def test_index_invites_the_user_when_empty(self) -> None:
        sync_iris_index(self.wiki, self.state, [])
        text = (self.wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        self.assertIn("매일 9시에 뉴스 3개 정리해줘", text)

    def test_routine_note_holds_the_request_and_its_history(self) -> None:
        rel = sync_routine_note(self.wiki, self.r)
        text = (self.wiki.user_root / rel).read_text(encoding="utf-8")
        self.assertIn("뉴스 3개 정리", text)
        self.assertIn("매일 09:00", text)
        self.assertIn("아직 실행된 적 없음", text)

        ran = record_result(
            self.db,
            collect_due(self.db, datetime(2026, 9, 29, 9, 0))[0][0],
            text="1. A\n2. B",
            now=datetime(2026, 9, 29, 9, 0),
        )
        sync_routine_note(self.wiki, ran)
        text2 = (self.wiki.user_root / rel).read_text(encoding="utf-8")
        self.assertIn("실행 1회", text2)
        self.assertIn("1. A", text2)

    def test_note_disappears_with_the_routine(self) -> None:
        sync_routine_note(self.wiki, self.r)
        delete_routine(self.db, self.r.id)
        self.assertTrue(remove_routine_note(self.wiki, self.r))
        self.assertFalse(remove_routine_note(self.wiki, self.r))

    def test_disabled_routine_is_shown_unchecked(self) -> None:
        off = update_routine(self.db, self.r.id, enabled=False)
        sync_iris_index(self.wiki, self.state, [off])
        text = (self.wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        self.assertIn("[ ] ", text)
        self.assertIn("켜짐 0개", text)

    def test_routine_note_renders_without_a_database(self) -> None:
        body = render_routine_note(self.r)
        self.assertIn("아침 뉴스 브리핑", body)
        self.assertIn("켜짐", body)


class ScheduleParsingTests(TestCase):
    def test_natural_time_forms(self) -> None:
        self.assertEqual(parse_time_of_day("9:00"), "09:00")
        self.assertEqual(parse_time_of_day("아침"), "09:00")
        self.assertEqual(parse_time_of_day("07:30"), "07:30")

    def test_korean_and_english_weekdays(self) -> None:
        self.assertEqual(parse_weekdays("월,수"), (0, 2))
        self.assertEqual(parse_weekdays("mon,wed"), (0, 2))
        self.assertEqual(parse_weekdays(""), tuple(range(7)))

    def test_descriptions_read_naturally(self) -> None:
        self.assertEqual(Schedule.build("daily", time_of_day="09:00").describe(), "매일 09:00")
        self.assertIn("월·금", Schedule.build("weekly", weekdays="mon,fri").describe())
        self.assertEqual(
            Schedule.build("interval", interval_minutes=120).describe(), "2시간마다"
        )

    def test_deliver_aliases(self) -> None:
        self.assertEqual(normalize_deliver("채팅,알림"), "chat,notify")
        self.assertEqual(normalize_deliver(""), "chat,notify")
        self.assertEqual(normalize_deliver("엉뚱한값"), "chat,notify")
