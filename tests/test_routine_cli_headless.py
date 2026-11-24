"""헤드리스 실행기 — 아이리스가 꺼져 있을 때 예약 루틴이 실제로 도는 경로.

여기는 사용자가 안 보는 사이 도는 코드다. 조용히 틀리면 알 방법이 없으므로
"아무것도 안 했다"와 "했다"를 둘 다 못박는다.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from iris.storage.database import Database
from iris.storage.routines import create_routine, get_routine, set_next_run


class _Env:
    """임시 DB·위키로 CLI 를 돌린다 — 진짜 사용자 데이터는 건드리지 않는다."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "cli.db"
        self._prev = os.environ.get("IRIS_DB_PATH")
        os.environ["IRIS_DB_PATH"] = str(self.db_path)

    def close(self) -> None:
        if self._prev is None:
            os.environ.pop("IRIS_DB_PATH", None)
        else:
            os.environ["IRIS_DB_PATH"] = self._prev
        self.tmp.cleanup()


class HeadlessRoutineTests(TestCase):
    def setUp(self) -> None:
        self.env = _Env()
        self.db = Database(self.env.db_path)
        self.wiki_root = self.env.root / "wiki"
        self.toasts: list[tuple[str, str]] = []
        self.replies: list[list[dict[str, str]]] = []

        from iris.knowledge.iris_wiki import IrisWiki

        self._wiki_patch = patch(
            "iris.knowledge.iris_wiki.default_user_wiki_root",
            return_value=self.wiki_root,
        )
        self._wiki_patch.start()
        self.IrisWiki = IrisWiki

    def tearDown(self) -> None:
        self._wiki_patch.stop()
        self.db.close()
        self.env.close()

    def _due_routine(self, **kwargs):
        r = create_routine(
            self.db,
            name=kwargs.pop("name", "아침 뉴스"),
            task=kwargs.pop("task", "뉴스 3개 정리해줘"),
            wake_when_closed=kwargs.pop("wake_when_closed", True),
            **kwargs,
        )
        set_next_run(
            self.db, r.id, (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
        )
        return get_routine(self.db, r.id)

    def _tick(self, reply: str = "1. A\n2. B\n3. C", *, running: bool = False, boom=None):
        from iris import routine_cli

        def _collect(route, messages, **kwargs):
            self.replies.append(messages)
            if boom is not None:
                raise boom
            return reply

        with (
            patch.object(routine_cli, "iris_is_running", return_value=running),
            patch("iris.config.settings.load_settings", return_value=self._settings()),
            patch("iris.ui.workers.backend_call.collect_reply", _collect),
            # 이 PC의 실제 Ollama에 임베딩을 요청하지 않게 — 키워드 검색만 돈다.
            patch(
                "iris.infrastructure.ollama_client.OllamaClient.pick_embedding_model",
                return_value="",
            ),
            patch(
                "iris.system.desktop_toast.show_toast",
                side_effect=lambda t, b, **k: self.toasts.append((t, b)) or True,
            ),
        ):
            return routine_cli.run_tick()

    def _settings(self):
        from iris.config.settings import Settings

        return Settings(
            ollama_model="qwen3:8b",
            ollama_base_url="http://127.0.0.1:11434/v1",
            agent_enabled=False,
        )

    def test_does_nothing_while_iris_is_open(self) -> None:
        """창이 떠 있으면 창이 처리한다 — 두 번 실행되면 결과가 두 번 간다."""
        r = self._due_routine()
        self._tick(running=True)
        self.assertEqual(get_routine(self.db, r.id).run_count, 0)
        self.assertEqual(self.toasts, [])

    def test_runs_a_due_routine_and_toasts_the_result(self) -> None:
        r = self._due_routine()
        code = self._tick()
        self.assertEqual(code, 0)

        after = get_routine(self.db, r.id)
        self.assertEqual(after.run_count, 1)
        self.assertEqual(after.last_status, "ok")
        self.assertIn("1. A", after.last_result)
        self.assertTrue(after.next_run_at)
        self.assertEqual(len(self.toasts), 1)
        self.assertEqual(self.toasts[0][0], "아침 뉴스")

    def test_sends_the_users_own_sentence_to_the_model(self) -> None:
        self._due_routine(task="오늘 날씨만 한 줄로 알려줘")
        self._tick()
        self.assertEqual(self.replies[0][-1]["content"], "오늘 날씨만 한 줄로 알려줘")

    def test_leaves_alone_routines_that_did_not_opt_in(self) -> None:
        """`wake_when_closed` 를 안 켠 루틴은 창이 열릴 때까지 기다린다."""
        r = self._due_routine(wake_when_closed=False)
        self._tick()
        self.assertEqual(get_routine(self.db, r.id).run_count, 0)
        self.assertEqual(self.toasts, [])

    def test_disabled_routine_is_not_run(self) -> None:
        from iris.storage.routines import update_routine

        r = self._due_routine()
        update_routine(self.db, r.id, enabled=False)
        self._tick()
        self.assertEqual(get_routine(self.db, r.id).run_count, 0)

    def test_nothing_due_exits_quietly(self) -> None:
        create_routine(self.db, name="나중", task="뭔가", wake_when_closed=True)
        self.assertEqual(self._tick(), 0)
        self.assertEqual(self.toasts, [])

    def test_model_failure_is_recorded_and_surfaced(self) -> None:
        r = self._due_routine()
        self._tick(boom=RuntimeError("Ollama HTTP 429: rate limit"))

        after = get_routine(self.db, r.id)
        self.assertEqual(after.last_status, "failed")
        self.assertIn("429", after.last_result)
        self.assertTrue(self.toasts)
        self.assertIn("실패", self.toasts[0][0])

    def test_long_outage_marks_the_run_missed_instead_of_backfilling(self) -> None:
        r = self._due_routine()
        set_next_run(
            self.db, r.id, (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        )
        self._tick()

        after = get_routine(self.db, r.id)
        self.assertEqual(after.run_count, 0)
        self.assertEqual(after.miss_count, 1)
        self.assertEqual(after.last_status, "missed")
        self.assertTrue(after.next_run_at)

    def test_result_reaches_the_wiki_routine_note(self) -> None:
        r = self._due_routine()
        self._tick()
        note = self.wiki_root / "IRIS" / "routines" / "아침-뉴스.md"
        self.assertTrue(note.is_file(), list(self.wiki_root.rglob("*.md")))
        text = note.read_text(encoding="utf-8")
        self.assertIn("실행 1회", text)
        self.assertIn("1. A", text)

    def test_pinned_model_is_used_when_running_headless(self) -> None:
        self._due_routine(model="qwen3:32b")
        used: list[str] = []

        from iris import routine_cli

        def _collect(route, messages, **kwargs):
            used.append(route.model)
            return "결과"

        with (
            patch.object(routine_cli, "iris_is_running", return_value=False),
            patch("iris.config.settings.load_settings", return_value=self._settings()),
            patch("iris.ui.workers.backend_call.collect_reply", _collect),
            # 이 PC의 실제 Ollama에 임베딩을 요청하지 않게 — 키워드 검색만 돈다.
            patch(
                "iris.infrastructure.ollama_client.OllamaClient.pick_embedding_model",
                return_value="",
            ),
            patch("iris.system.desktop_toast.show_toast", return_value=True),
        ):
            routine_cli.run_tick()
        self.assertEqual(used, ["qwen3:32b"])

    def test_past_history_is_given_like_the_app_does(self) -> None:
        """창이 닫혀 있어도 창이 열렸을 때와 같은 History 근거가 들어간다."""
        from iris.knowledge.history_store import KIND_CHAT, record_entry
        from iris.knowledge.history_index import index_entry

        entry = record_entry(self.db, kind=KIND_CHAT, body="날씨는 기상청 단기예보로 봐 달라고 했습니다")
        index_entry(self.db, entry)
        self._due_routine(task="오늘 날씨만 한 줄로 알려줘")
        self._tick()
        system = self.replies[0][0]["content"]
        self.assertIn("기상청 단기예보", system)


class RunningDetectionTests(TestCase):
    def test_missing_endpoint_file_means_not_running(self) -> None:
        from iris import routine_cli

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "iris.system.control_surface.control_state_dir",
                return_value=Path(tmp),
            ):
                self.assertFalse(routine_cli.iris_is_running())

    def test_stale_port_file_with_dead_process_means_not_running(self) -> None:
        """앱이 비정상 종료하면 파일이 남는다 — 그걸 '떠 있음'으로 보면 안 된다."""
        from iris import routine_cli

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "control_port").write_text("59999", encoding="utf-8")
            (root / "control_host").write_text("127.0.0.1", encoding="utf-8")
            with patch(
                "iris.system.control_surface.control_state_dir", return_value=root
            ):
                self.assertFalse(routine_cli.iris_is_running())
