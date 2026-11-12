"""MainWindow 배선 — History 기록, 모델 전환 시 맥락 이관, 자동 전환 체인 구성.

창을 통째로 띄우지 않고 메서드를 스텁에 바인딩해 호출한다(이 저장소의 기존 방식).
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
_APP = QApplication.instance() or QApplication(sys.argv)

from iris.knowledge.history_store import count_entries, list_entries  # noqa: E402
from iris.knowledge.iris_wiki import IrisWiki  # noqa: E402
from iris.runtime.model_switch import ModelSwitchService  # noqa: E402
from iris.storage.database import Database  # noqa: E402
from iris.storage.failover_prefs import (  # noqa: E402
    FallbackEntry,
    save_failover_settings,
)
from iris.ui.window.main_window import MainWindow  # noqa: E402


def _boom(*args, **kwargs):
    raise RuntimeError("디스크 꽉참")


class _Activity:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append_instant_line(self, line: str) -> None:
        self.lines.append(line)

    def joined(self) -> str:
        return "\n".join(self.lines)


class _Chat:
    def __init__(self) -> None:
        self.ended: list[str | None] = []
        self.messages: list[tuple[str, str]] = []
        self.selected: list[str] = []

    def end_stream_message(self, final_text=None) -> None:
        self.ended.append(final_text)

    def append_message_instant(self, who: str, text: str) -> None:
        self.messages.append((who, text))

    def append_note(self, text: str) -> None:
        self.messages.append(("note", text))

    def select_model_silent(self, model: str) -> bool:
        self.selected.append(model)
        return True


class _Header:
    def __init__(self) -> None:
        self.model = ""

    def set_model_name(self, name: str) -> None:
        self.model = name


class ContextHandoffWiringTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "w.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        self.activity = _Activity()
        self.chat = _Chat()

        self.win = SimpleNamespace(
            _db=self.db,
            _iris_wiki=self.wiki,
            _model_switch=ModelSwitchService(self.db, wiki=self.wiki),
            _live_activity=self.activity,
            _chat=self.chat,
            _status_header=_Header(),
            _conversation_id=42,
            _pending_handoff="",
            _last_archive_id="",
            _saved_model="",
            _history=[],
            _context_limit_cache={},
            _settings=SimpleNamespace(
                ollama_model="paid:big",
                ollama_base_url="http://127.0.0.1:11434",
                hermes_enabled=False,
            ),
            _history_embed_worker=None,
            _use_hermes_backend=lambda: False,
        )
        # 창을 띄우지 않으므로 서로 부르는 메서드는 스텁에 직접 매어 준다.
        for name in (
            "_route_target_for",
            "_history_fits",
            "_context_limit_for",
            "_handoff_messages_for",
            "_record_wiki_history",
            "_fallback_targets",
            "_payload_for_candidate",
            "_summary_route_for",
            "_start_handoff_summary",
            "_cancel_handoff_summary",
            "_on_handoff_summary_ready",
            "_on_handoff_evidence_ready",
            "failover_wants_summary",
        ):
            setattr(self.win, name, types.MethodType(getattr(MainWindow, name), self.win))
        self.win._pending_handoff_ctx = None
        self.win._handoff_summary_worker = None
        self.win._busy = False
        self.win._chat_messages_with_project_context = lambda: list(self.win._history)
        self.win._kick_history_embed = lambda: None
        # 의미검색 워커는 띄우지 않고 요청만 받아 둔다.
        self.evidence_requests: list[tuple[list, object]] = []
        self.win._start_handoff_evidence = lambda h, c: self.evidence_requests.append((h, c))

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    # --- 기록 -------------------------------------------------------

    def test_turns_land_in_wiki_history(self) -> None:
        MainWindow._record_wiki_history(self.win, "chat", "설치가 안 됩니다", role="user")
        MainWindow._record_wiki_history(self.win, "chat", "권한 문제입니다", role="assistant")
        MainWindow._record_wiki_history(
            self.win, "action", "setup.ps1 실행", title="설치 재시도"
        )

        self.assertEqual(count_entries(self.db), 3)
        entries = list_entries(self.db, conversation_id=42)
        self.assertEqual({e.kind for e in entries}, {"chat", "action"})
        self.assertTrue((self.wiki.user_root / "history").exists())

    def test_recording_failure_does_not_break_the_turn(self) -> None:
        self.win._model_switch = SimpleNamespace(record=_boom)
        MainWindow._record_wiki_history(self.win, "chat", "본문", role="user")
        self.assertIn("History 기록 스킵", self.activity.joined())

    # --- 맥락 이관 ---------------------------------------------------

    def test_no_handoff_without_conversation(self) -> None:
        MainWindow._handoff_context_to(self.win, "paid:big", "free:small")
        self.assertEqual(self.win._pending_handoff, "")
        self.assertEqual(self.activity.lines, [])

    def test_short_history_is_passed_verbatim_not_summarized(self) -> None:
        """새 모델에 원문이 다 들어가면 요약하지 않는다 — 원문이 더 정확하다."""
        self.win._history = [
            {"role": "user", "content": "설치 권한 오류"},
            {"role": "assistant", "content": "소유권을 고치세요"},
        ]
        self.win._context_limit_cache["free:small"] = 128_000

        MainWindow._handoff_context_to(self.win, "paid:big", "free:small")

        self.assertEqual(self.win._pending_handoff, "")
        self.assertIn("원문 2턴 그대로 전달", self.activity.joined())
        # 원문은 그래도 아카이브에 남아야 한다
        self.assertTrue(self.win._last_archive_id)

    def test_oversized_history_is_summarized_for_the_small_model(self) -> None:
        self.win._history = [
            {"role": "user", "content": "설치 프로그램 권한 오류를 고쳐줘"},
            {"role": "assistant", "content": "가" * 20000},
            {"role": "user", "content": "0.1.16으로 올려줘"},
        ]
        self.win._context_limit_cache["free:small"] = 4096

        MainWindow._handoff_context_to(self.win, "paid:big", "free:small")

        self.assertTrue(self.win._pending_handoff)
        self.assertIn("컨텍스트가 좁아 요약", self.activity.joined())
        # 요약이어도 사용자 요구사항은 글자 그대로 넘어가야 한다
        self.assertIn("0.1.16으로 올려줘", self.win._pending_handoff)
        self.assertIn("설치 프로그램 권한 오류를 고쳐줘", self.win._pending_handoff)

    def test_switch_is_recorded_even_when_passed_verbatim(self) -> None:
        self.win._history = [{"role": "user", "content": "질문"}]
        self.win._context_limit_cache["free:small"] = 128_000
        MainWindow._handoff_context_to(self.win, "paid:big", "free:small")

        switches = [e for e in list_entries(self.db) if e.tags == "model-switch"]
        self.assertTrue(switches)

    # --- 자동 전환 체인 ----------------------------------------------

    def test_no_chain_when_failover_has_no_candidates(self) -> None:
        attempts = MainWindow._fallback_attempts(
            self.win, "paid:big", [{"role": "user", "content": "q"}]
        )
        self.assertEqual([a.model for a in attempts], ["paid:big"])

    def test_chain_uses_configured_free_models(self) -> None:
        settings = self.win._model_switch.failover_settings
        settings.chain = [
            FallbackEntry(model="free:a", backend="ollama"),
            FallbackEntry(model="free:b", backend="ollama"),
        ]
        save_failover_settings(self.db, settings)
        self.win._context_limit_cache.update(
            {"paid:big": 128_000, "free:a": 128_000, "free:b": 128_000}
        )

        msgs = [{"role": "user", "content": "질문"}]
        attempts = MainWindow._fallback_attempts(self.win, "paid:big", msgs)

        self.assertEqual([a.model for a in attempts], ["paid:big", "free:a", "free:b"])
        # 컨텍스트가 넉넉하면 후보도 원문을 받는다
        self.assertEqual(attempts[1].messages, msgs)

    def test_chain_skips_backends_this_worker_cannot_reach(self) -> None:
        """이 워커는 Ollama 전용이다 — API 후보를 넣으면 무조건 실패한다."""
        settings = self.win._model_switch.failover_settings
        settings.chain = [
            FallbackEntry(model="remote:x", backend="api"),
            FallbackEntry(model="free:a", backend="ollama"),
        ]
        save_failover_settings(self.db, settings)
        self.win._context_limit_cache.update({"paid:big": 128_000, "free:a": 128_000})

        attempts = MainWindow._fallback_attempts(
            self.win, "paid:big", [{"role": "user", "content": "q"}]
        )
        self.assertEqual([a.model for a in attempts], ["paid:big", "free:a"])

    def test_small_fallback_gets_a_summarized_payload(self) -> None:
        settings = self.win._model_switch.failover_settings
        settings.chain = [FallbackEntry(model="tiny:free", backend="ollama")]
        save_failover_settings(self.db, settings)
        self.win._history = [
            {"role": "user", "content": "원래 요구사항이다"},
            {"role": "assistant", "content": "나" * 20000},
        ]
        self.win._context_limit_cache.update({"paid:big": 128_000, "tiny:free": 2048})

        big_msgs = [{"role": "user", "content": "나" * 20000}]
        attempts = MainWindow._fallback_attempts(self.win, "paid:big", big_msgs)

        self.assertEqual(len(attempts), 2)
        self.assertNotEqual(attempts[1].messages, big_msgs)
        self.assertEqual(attempts[1].messages[0]["role"], "system")
        self.assertIn("원래 요구사항이다", attempts[1].messages[0]["content"])



    # --- 구 모델 인수인계 요약 ----------------------------------------

    def test_summary_route_picks_the_backend_in_use(self) -> None:
        from types import SimpleNamespace as NS

        self.win._use_hermes_backend = lambda: False
        route = MainWindow._summary_route_for(self.win, "qwen3:8b")
        self.assertEqual(route.backend, "ollama")
        self.assertEqual(route.model, "qwen3:8b")

        self.win._use_hermes_backend = lambda: True
        self.win._settings.hermes_base_url = "http://127.0.0.1:8642/v1"
        self.win._settings.hermes_api_key = "k"
        self.win._settings.hermes_command = "hermes"
        with patch(
            "iris.infrastructure.iris_agent_client.resolve_iris_agent_inference",
            return_value=NS(model="upstream", label="up"),
        ):
            route = MainWindow._summary_route_for(self.win, "qwen3:8b")
        self.assertEqual(route.backend, "hermes")
        self.assertEqual(route.target.model, "upstream")

    def test_summary_route_api_model_skips_hermes(self) -> None:
        """Hermes 켜져 있어도 Iris API runtime 제목/요약은 제공자 직행."""
        from iris.storage.api_providers import ApiProvider

        self.win._use_hermes_backend = lambda: True
        provider = ApiProvider(
            id="nv1",
            name="NVIDIA",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="sk",
            models=["nvidia/nemotron-mini"],
        )
        with patch(
            "iris.ui.window.main_window.get_api_provider", return_value=provider
        ):
            route = MainWindow._summary_route_for(
                self.win, "api:nv1:nvidia/nemotron-mini"
            )
        self.assertIsNotNone(route)
        self.assertEqual(route.backend, "api")
        self.assertEqual(route.model, "nvidia/nemotron-mini")

    def test_summary_route_is_none_when_it_cannot_resolve(self) -> None:
        self.win._use_hermes_backend = lambda: True
        with patch(
            "iris.ui.window.main_window.get_api_provider",
            return_value=None,
        ):
            self.assertIsNone(MainWindow._summary_route_for(self.win, "api:gone:x"))
        self.assertIsNone(MainWindow._summary_route_for(self.win, "   "))

    def test_summary_is_not_requested_when_the_setting_is_off(self) -> None:
        settings = self.win._model_switch.failover_settings
        settings.ask_old_model_summary = False
        save_failover_settings(self.db, settings)
        self.win._use_hermes_backend = lambda: False

        started = []
        self.win._summary_route_for = lambda *a: started.append(1)
        MainWindow._start_handoff_summary(self.win, "old", SimpleNamespace())
        self.assertEqual(started, [])

    def test_late_summary_replaces_the_rule_based_text(self) -> None:
        self.win._history = [
            {"role": "user", "content": "원래 요구사항"},
            {"role": "assistant", "content": "가" * 20000},
        ]
        self.win._context_limit_cache["tiny:free"] = 2048
        self.win._start_handoff_summary = lambda *a: None
        MainWindow._handoff_context_to(self.win, "paid:big", "tiny:free")

        self.assertTrue(self.win._pending_handoff)
        self.assertFalse(self.win._pending_handoff_ctx.llm_written)
        archive_id = self.win._pending_handoff_ctx.archive_id

        MainWindow._on_handoff_summary_ready(
            self.win, "## 1. 현재 목표와 상태\n구 모델이 직접 쓴 요약", archive_id
        )
        self.assertIn("구 모델이 직접 쓴 요약", self.win._pending_handoff)
        self.assertTrue(self.win._pending_handoff_ctx.llm_written)

    def test_summary_is_dropped_once_the_turn_went_out(self) -> None:
        self.win._history = [{"role": "user", "content": "요구사항 " * 2000}]
        self.win._context_limit_cache["tiny:free"] = 128
        self.win._start_handoff_summary = lambda *a: None
        MainWindow._handoff_context_to(self.win, "paid:big", "tiny:free")
        before = self.win._pending_handoff
        archive_id = self.win._pending_handoff_ctx.archive_id

        self.win._busy = True  # 요청이 이미 나갔다
        MainWindow._on_handoff_summary_ready(self.win, "늦게 온 요약", archive_id)
        self.assertEqual(self.win._pending_handoff, before)

    def test_stale_summary_from_a_previous_switch_is_ignored(self) -> None:
        self.win._history = [{"role": "user", "content": "요구사항"}]
        self.win._context_limit_cache["tiny:free"] = 128
        self.win._start_handoff_summary = lambda *a: None
        MainWindow._handoff_context_to(self.win, "paid:big", "tiny:free")
        before = self.win._pending_handoff

        MainWindow._on_handoff_summary_ready(self.win, "낡은 요약", "다른아카이브id")
        self.assertEqual(self.win._pending_handoff, before)

    def test_summary_ignored_when_nothing_is_pending(self) -> None:
        self.win._pending_handoff = ""
        self.win._pending_handoff_ctx = None
        MainWindow._on_handoff_summary_ready(self.win, "요약", "a1")
        self.assertEqual(self.win._pending_handoff, "")

    # --- 의미검색 발췌 -----------------------------------------------

    def _summarized_switch(self) -> str:
        self.win._history = [
            {"role": "user", "content": "설치 프로그램이 권한 때문에 죽어요"},
            {"role": "assistant", "content": "가" * 20000},
        ]
        self.win._context_limit_cache["tiny:free"] = 2048
        self.win._start_handoff_summary = lambda *a: None
        MainWindow._handoff_context_to(self.win, "paid:big", "tiny:free")
        return self.win._pending_handoff_ctx.archive_id

    def test_summarized_switch_asks_for_semantic_evidence(self) -> None:
        archive_id = self._summarized_switch()
        self.assertEqual(len(self.evidence_requests), 1)
        history, context = self.evidence_requests[0]
        self.assertEqual(history, self.win._history)
        self.assertEqual(context.archive_id, archive_id)

    def test_verbatim_switch_does_not_ask_for_evidence(self) -> None:
        """원문이 그대로 가면 발췌도 안 붙는다 — 찾아 봐야 버린다."""
        self.win._history = [{"role": "user", "content": "짧은 대화"}]
        self.win._context_limit_cache["big:other"] = 128_000
        MainWindow._handoff_context_to(self.win, "paid:big", "big:other")
        self.assertEqual(self.evidence_requests, [])

    def test_late_evidence_replaces_the_keyword_excerpt(self) -> None:
        archive_id = self._summarized_switch()
        block = "# 아이리스 위키 History 발췌\n\n## 의미검색으로 찾은 venv 소유권 해결"
        MainWindow._on_handoff_evidence_ready(self.win, block, archive_id)
        self.assertIn("의미검색으로 찾은 venv 소유권 해결", self.win._pending_handoff)
        self.assertEqual(self.win._pending_handoff_ctx.wiki_block, block)

    def test_evidence_and_summary_both_survive_in_either_order(self) -> None:
        archive_id = self._summarized_switch()
        MainWindow._on_handoff_evidence_ready(self.win, "## 의미 발췌", archive_id)
        MainWindow._on_handoff_summary_ready(self.win, "## 1. 구 모델 요약", archive_id)
        self.assertIn("의미 발췌", self.win._pending_handoff)
        self.assertIn("구 모델 요약", self.win._pending_handoff)

    def test_evidence_is_dropped_when_stale_busy_or_empty(self) -> None:
        archive_id = self._summarized_switch()
        before = self.win._pending_handoff
        MainWindow._on_handoff_evidence_ready(self.win, "## 낡은 발췌", "다른아카이브id")
        MainWindow._on_handoff_evidence_ready(self.win, "   ", archive_id)
        self.win._busy = True
        MainWindow._on_handoff_evidence_ready(self.win, "## 늦은 발췌", archive_id)
        self.assertEqual(self.win._pending_handoff, before)

    def test_verbatim_switch_cancels_any_running_summary(self) -> None:
        """원문이 다 들어가면 요약은 필요 없다 — 돌던 것도 세운다."""
        cancelled = []
        self.win._cancel_handoff_summary = lambda: cancelled.append(1)
        self.win._history = [{"role": "user", "content": "짧은 대화"}]
        self.win._context_limit_cache["big:other"] = 128_000

        MainWindow._handoff_context_to(self.win, "paid:big", "big:other")
        self.assertEqual(cancelled, [1])
        self.assertIsNone(self.win._pending_handoff_ctx)

    # --- Hermes 경로 체인 --------------------------------------------

    def test_hermes_chain_resolves_targets_on_the_ui_thread(self) -> None:
        """워커는 DB를 못 만진다 — 후보 타깃을 여기서 미리 풀어 넘겨야 한다."""
        from types import SimpleNamespace as NS

        settings = self.win._model_switch.failover_settings
        settings.chain = [
            FallbackEntry(model="free:a", backend="ollama"),
            FallbackEntry(model="api:zz:remote", backend="api"),
        ]
        save_failover_settings(self.db, settings)
        self.win._settings.hermes_enabled = True
        self.win._use_hermes_backend = lambda: True
        self.win._context_limit_cache.update(
            {"paid:big": 128_000, "free:a": 128_000, "api:zz:remote": 128_000}
        )

        resolved = {
            "free:a": NS(model="free-upstream", label="free A"),
            "api:zz:remote": NS(model="vendor/remote-v2", label="remote"),
        }
        msgs = [{"role": "user", "content": "질문"}]
        primary = NS(model="big-upstream", label="big")

        with patch(
            "iris.infrastructure.iris_agent_client.resolve_iris_agent_inference",
            side_effect=lambda m, **kw: resolved[m],
        ):
            attempts = MainWindow._hermes_fallback_attempts(
                self.win, "paid:big", msgs, primary
            )

        # Hermes 는 Ollama 이름과 api: id 를 모두 받는다 — 백엔드로 거르지 않는다
        self.assertEqual(
            [a.model for a in attempts], ["paid:big", "free:a", "api:zz:remote"]
        )
        self.assertEqual(attempts[0].target, primary)
        self.assertEqual(attempts[1].target.model, "free-upstream")
        self.assertEqual(attempts[2].target.model, "vendor/remote-v2")

    def test_hermes_chain_drops_candidates_it_cannot_resolve(self) -> None:
        """설정에서 지워진 API 같은 후보는 조용히 뺀다."""
        from types import SimpleNamespace as NS

        settings = self.win._model_switch.failover_settings
        settings.chain = [
            FallbackEntry(model="api:gone:x", backend="api"),
            FallbackEntry(model="free:a", backend="ollama"),
        ]
        save_failover_settings(self.db, settings)
        self.win._use_hermes_backend = lambda: True
        self.win._context_limit_cache.update({"paid:big": 128_000, "free:a": 128_000})

        def _resolve(model, **kwargs):
            if model == "api:gone:x":
                raise ValueError("선택한 API가 없습니다")
            return NS(model="free-upstream", label="free A")

        with patch(
            "iris.infrastructure.iris_agent_client.resolve_iris_agent_inference",
            side_effect=_resolve,
        ):
            attempts = MainWindow._hermes_fallback_attempts(
                self.win, "paid:big", [{"role": "user", "content": "q"}], NS(label="big")
            )

        self.assertEqual([a.model for a in attempts], ["paid:big", "free:a"])

    def test_hermes_chain_compresses_for_small_candidates(self) -> None:
        from types import SimpleNamespace as NS

        settings = self.win._model_switch.failover_settings
        settings.chain = [FallbackEntry(model="tiny:free", backend="ollama")]
        save_failover_settings(self.db, settings)
        self.win._use_hermes_backend = lambda: True
        self.win._history = [{"role": "user", "content": "원래 요구사항이다"}]
        self.win._context_limit_cache.update({"paid:big": 128_000, "tiny:free": 1024})

        big = [{"role": "user", "content": "나" * 20000}]
        with patch(
            "iris.infrastructure.iris_agent_client.resolve_iris_agent_inference",
            side_effect=lambda m, **kw: NS(model="tiny-upstream", label="tiny"),
        ):
            attempts = MainWindow._hermes_fallback_attempts(
                self.win, "paid:big", big, NS(label="big")
            )

        self.assertNotEqual(attempts[1].messages, big)
        self.assertIn("원래 요구사항이다", attempts[1].messages[0]["content"])

    # --- 전환 통지 ---------------------------------------------------

    def test_switch_notice_updates_selection_and_clears_partial_text(self) -> None:
        MainWindow._on_chat_model_switched(self.win, "free:small", "할당량 소진", True)

        self.assertEqual(self.chat.ended, [""])  # 앞 모델 조각 제거
        self.assertEqual(self.chat.selected, ["free:small"])
        self.assertEqual(self.win._settings.ollama_model, "free:small")
        self.assertEqual(self.win._status_header.model, "free:small")
        self.assertIn("할당량 소진", self.chat.messages[-1][1])
        self.assertEqual(self.chat.messages[-1][0], "note")

    def test_switch_without_partial_text_leaves_the_stream_alone(self) -> None:
        MainWindow._on_chat_model_switched(self.win, "free:small", "서버 오류", False)
        self.assertEqual(self.chat.ended, [])
        self.assertIn("서버 오류", self.activity.joined())


    def test_preparing_candidates_records_nothing(self) -> None:
        """후보 준비는 매 턴 일어난다 — 일어나지도 않은 전환이 기록되면 안 된다."""
        from iris.runtime.context_archive import latest_snapshot

        settings = self.win._model_switch.failover_settings
        settings.chain = [FallbackEntry(model="tiny:free", backend="ollama")]
        save_failover_settings(self.db, settings)
        self.win._history = [{"role": "user", "content": "원래 요구사항"}]
        self.win._context_limit_cache.update({"paid:big": 128_000, "tiny:free": 512})

        before = count_entries(self.db)
        for _ in range(3):
            MainWindow._fallback_attempts(
                self.win, "paid:big", [{"role": "user", "content": "나" * 5000}]
            )

        self.assertEqual(count_entries(self.db), before)
        self.assertEqual([e for e in list_entries(self.db) if e.tags == "model-switch"], [])
        self.assertIsNone(latest_snapshot(self.db, 42))

    def test_actual_worker_switch_is_recorded_once(self) -> None:
        MainWindow._on_chat_model_switched(self.win, "free:small", "할당량 소진", False)

        switches = [e for e in list_entries(self.db) if e.tags == "model-switch"]
        self.assertEqual(len(switches), 1)
        self.assertIn("paid:big", switches[0].body)
        self.assertIn("free:small", switches[0].body)

    # --- 컨텍스트 적합 판정 -------------------------------------------

    def test_fits_uses_eighty_percent_of_the_window(self) -> None:
        self.win._context_limit_cache["m"] = 1000
        small = [{"role": "user", "content": "가" * 100}]
        self.assertTrue(MainWindow._history_fits(self.win, "m", small))
        big = [{"role": "user", "content": "가" * 100000}]
        self.assertFalse(MainWindow._history_fits(self.win, "m", big))

    def test_fits_defaults_to_true_when_the_limit_is_unknown(self) -> None:
        """한도를 못 읽었다고 멀쩡한 원문을 요약해버리면 안 된다."""
        broken = SimpleNamespace()
        self.assertTrue(
            MainWindow._history_fits(broken, "m", [{"role": "user", "content": "x"}])
        )
