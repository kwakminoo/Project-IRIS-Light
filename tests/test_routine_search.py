"""루틴 웹 검색 — 실제 자료를 모델에 쥐여주는 단계.

이 단계가 없으면 모델이 "오늘 뉴스 3개"에 가짜 헤드라인을 지어낸다(gemma4 실측).
그래서 "검색이 돌았나"보다 **"실패했을 때 무엇이 모델에게 가나"** 를 더 단단히 잡는다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from iris.runtime.routine_runner import build_run_messages
from iris.runtime.routine_search import (
    SearchHit,
    SearchOutcome,
    format_evidence,
    parse_results,
    run_search,
)
from iris.storage.database import Database
from iris.storage.routines import create_routine, get_routine, update_routine

_NEWS_PAYLOAD = {
    "news_results": [
        {
            "title": "반도체주 급락…엔비디아만 버텼다",
            "link": "https://example.com/1",
            "source": {"name": "한국경제"},
            "date": "09/29/2026, 08:00 AM",
        },
        {
            "title": "정부 초과 세수 활용 계획 발표",
            "link": "https://example.com/2",
            "source": "연합인포맥스",
            "date": "09/29/2026, 02:51 AM",
        },
    ]
}


class ParsingTests(TestCase):
    def test_reads_news_results(self) -> None:
        hits = parse_results(_NEWS_PAYLOAD)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].source, "한국경제")
        self.assertEqual(hits[1].source, "연합인포맥스")

    def test_falls_back_to_organic_results(self) -> None:
        hits = parse_results({"organic_results": [{"title": "웹 결과", "snippet": "요약"}]})
        self.assertEqual(hits[0].title, "웹 결과")
        self.assertEqual(hits[0].snippet, "요약")

    def test_rows_without_a_title_are_dropped(self) -> None:
        hits = parse_results({"news_results": [{"link": "x"}, {"title": "살아남음"}]})
        self.assertEqual([h.title for h in hits], ["살아남음"])

    def test_empty_payload_is_not_an_error(self) -> None:
        self.assertEqual(parse_results({}), [])

    def test_limit_is_respected(self) -> None:
        self.assertEqual(len(parse_results(_NEWS_PAYLOAD, limit=1)), 1)


class EvidenceTests(TestCase):
    def test_success_block_pins_the_model_to_the_sources(self) -> None:
        out = SearchOutcome(
            hits=parse_results(_NEWS_PAYLOAD),
            query="한국 주요 뉴스",
            fetched_at="2026-09-29T09:00:00",
        )
        block = format_evidence(out)
        self.assertIn("반도체주 급락", block)
        self.assertIn("한국경제", block)
        self.assertIn("https://example.com/1", block)
        self.assertNotIn("덧붙이지 마라", block)

    def test_headline_only_results_tell_the_model_titles_are_the_content(self) -> None:
        """google_news 는 본문을 안 준다 — 안 알려주면 '내용을 알 수 없다'고 답한다."""
        out = SearchOutcome(hits=parse_results(_NEWS_PAYLOAD), query="q")
        self.assertIn("본문 요약 없음", format_evidence(out))

    def test_results_with_snippets_do_not_get_that_hint(self) -> None:
        out = SearchOutcome(
            hits=[SearchHit(title="t", snippet="본문 요약이 있다")], query="q"
        )
        self.assertNotIn("본문 요약 없음", format_evidence(out))

    def test_failure_is_stated_not_silently_dropped(self) -> None:
        """빈 문자열을 주면 모델은 검색이 없었던 줄 알고 지어낸다."""
        block = format_evidence(SearchOutcome(query="뉴스", error="SerpApi 키가 없습니다"))
        self.assertIn("상태: 실패", block)
        self.assertIn("SerpApi 키가 없습니다", block)
        self.assertNotIn("지어내지 말고", block)
        self.assertTrue(block.strip())


class RunSearchTests(TestCase):
    def test_blank_query_never_hits_the_network(self) -> None:
        with patch("iris.infrastructure.serpapi_client.search") as called:
            out = run_search("   ")
            called.assert_not_called()
        self.assertEqual(out.error, "검색어 없음")

    def test_korean_locale_is_sent(self) -> None:
        """hl/gl 없이 보내면 몇 년 지난 미국 기사가 섞여 온다."""
        seen: dict = {}

        def _fake(query, **kwargs):
            seen.update(kwargs)
            return _NEWS_PAYLOAD

        with patch("iris.infrastructure.serpapi_client.search", _fake):
            out = run_search("뉴스", api_key="k")
        self.assertTrue(out.ok)
        self.assertEqual(seen.get("hl"), "ko")
        self.assertEqual(seen.get("gl"), "kr")
        self.assertEqual(seen.get("engine"), "google_news")

    def test_upstream_error_becomes_an_outcome_not_an_exception(self) -> None:
        with patch(
            "iris.infrastructure.serpapi_client.search",
            return_value={"error": "Your account has run out of searches."},
        ):
            out = run_search("뉴스", api_key="k")
        self.assertFalse(out.ok)
        self.assertIn("run out of searches", out.error)

    def test_thrown_exception_is_caught(self) -> None:
        with patch(
            "iris.infrastructure.serpapi_client.search",
            side_effect=OSError("네트워크 끊김"),
        ):
            out = run_search("뉴스", api_key="k")
        self.assertFalse(out.ok)
        self.assertIn("네트워크", out.error)

    def test_empty_results_are_reported(self) -> None:
        with patch("iris.infrastructure.serpapi_client.search", return_value={}):
            out = run_search("없는말", api_key="k")
        self.assertEqual(out.error, "검색 결과 없음")


class RoutineSearchFieldTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "r.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_search_defaults_to_off(self) -> None:
        r = create_routine(self.db, name="계산", task="1+1")
        self.assertEqual(r.search, "")
        self.assertEqual(r.search_engine, "google_news")

    def test_search_round_trips_and_can_be_cleared(self) -> None:
        r = create_routine(self.db, name="뉴스", task="뉴스 3개", search="한국 속보")
        self.assertEqual(get_routine(self.db, r.id).search, "한국 속보")
        self.assertEqual(update_routine(self.db, r.id, search="환율").search, "환율")
        self.assertEqual(update_routine(self.db, r.id, search="").search, "")

    def test_engine_can_be_changed(self) -> None:
        r = create_routine(self.db, name="주가", task="주가", search="삼성전자")
        changed = update_routine(self.db, r.id, search_engine="google_finance")
        self.assertEqual(changed.search_engine, "google_finance")


class RunPromptTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "r.db")
        self.r = create_routine(self.db, name="뉴스", task="오늘 뉴스 3개 정리")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_evidence_is_carried_into_the_prompt(self) -> None:
        out = SearchOutcome(hits=parse_results(_NEWS_PAYLOAD), query="뉴스")
        msgs = build_run_messages(self.r, evidence=format_evidence(out))
        self.assertIn("반도체주 급락", msgs[0]["content"])
        self.assertEqual(msgs[-1]["content"], "오늘 뉴스 3개 정리")

    def test_toolless_backend_is_told_it_cannot_browse(self) -> None:
        """이 문장이 빠지면 gemma4 가 가짜 헤드라인을 지어냈다."""
        content = build_run_messages(self.r, tools_available=False)[0]["content"]
        self.assertIn("웹 검색", content)
        self.assertIn("쓸 수 없다", content)
        self.assertNotIn("실시간 정보를 가져올 수 없습니다", content)

    def test_backend_with_tools_is_not_told_that(self) -> None:
        self.assertNotIn("웹 검색", build_run_messages(self.r)[0]["content"])

    def test_search_evidence_and_no_tools_can_coexist(self) -> None:
        """검색으로 자료를 줬으면 도구가 없어도 답할 수 있어야 한다."""
        out = SearchOutcome(hits=parse_results(_NEWS_PAYLOAD), query="뉴스")
        content = build_run_messages(
            self.r, evidence=format_evidence(out), tools_available=False
        )[0]["content"]
        self.assertIn("반도체주 급락", content)
        self.assertIn("쓸 수 없다", content)
        self.assertNotIn("실시간 정보를 가져올 수 없습니다", content)
