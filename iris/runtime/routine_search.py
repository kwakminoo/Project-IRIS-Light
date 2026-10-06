"""루틴 실행 전 웹 검색 — 모델에게 **실제 자료**를 쥐여준다.

모델에게 도구를 주고 알아서 부르길 기대하지 않는다. 이유가 둘이다.

- Ollama 직행·커스텀 API 경로에는 도구가 아예 없다. 그 상태로 "오늘 뉴스 3개"를
  시키면 모델은 자기가 검색을 못 한다는 걸 모른 채 **그럴듯한 가짜 헤드라인을
  지어낸다**(gemma4 로 실측 확인).
- 루틴은 사용자가 안 보는 새벽에도 돈다. 도구 호출이 한 번 실패하면 아무도 모른다.

그래서 IRIS 가 먼저 검색해서 결과를 근거 블록으로 넣고, 모델은 그걸 정리만 한다.
검색어는 루틴에 **명시적으로** 저장한다 — 할 일 문장에서 추측하지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

# 한국어 질의인데 이걸 안 주면 미국 기준 결과가 와서 몇 년 지난 기사가 섞인다.
DEFAULT_HL = "ko"
DEFAULT_GL = "kr"
DEFAULT_ENGINE = "google_news"
DEFAULT_COUNT = 6
MAX_COUNT = 20

# SerpApi 응답에서 결과가 담기는 자리 — 엔진마다 이름이 다르다.
_RESULT_KEYS = ("news_results", "organic_results", "top_stories", "local_results")


@dataclass(frozen=True)
class SearchHit:
    title: str
    link: str = ""
    source: str = ""
    date: str = ""
    snippet: str = ""

    def as_line(self) -> str:
        bits = [f"- **{self.title}**"]
        meta = " · ".join(x for x in (self.source, self.date) if x)
        if meta:
            bits.append(f" ({meta})")
        if self.snippet:
            bits.append(f"\n  {self.snippet}")
        if self.link:
            bits.append(f"\n  {self.link}")
        return "".join(bits)


@dataclass(frozen=True)
class SearchOutcome:
    hits: list[SearchHit] = field(default_factory=list)
    query: str = ""
    engine: str = ""
    error: str = ""
    fetched_at: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.hits) and not self.error


def _text(value: object) -> str:
    if isinstance(value, dict):
        for key in ("name", "title", "snippet"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value or "").strip()


def parse_results(payload: dict, *, limit: int = DEFAULT_COUNT) -> list[SearchHit]:
    """SerpApi 응답 → 결과 목록. 엔진별로 키가 달라 알려진 자리를 훑는다."""
    rows: list = []
    for key in _RESULT_KEYS:
        found = payload.get(key)
        if isinstance(found, list) and found:
            rows = found
            break
    hits: list[SearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"))
        if not title:
            continue
        hits.append(
            SearchHit(
                title=title,
                link=_text(row.get("link")),
                source=_text(row.get("source")),
                date=_text(row.get("date")),
                snippet=_text(row.get("snippet"))[:300],
            )
        )
        if len(hits) >= max(1, int(limit)):
            break
    return hits


def run_search(
    query: str,
    *,
    engine: str = DEFAULT_ENGINE,
    count: int = DEFAULT_COUNT,
    hl: str = DEFAULT_HL,
    gl: str = DEFAULT_GL,
    api_key: str = "",
) -> SearchOutcome:
    """검색을 돌린다. 실패해도 예외를 올리지 않고 `error` 에 담는다."""
    text = str(query or "").strip()
    stamp = datetime.now().isoformat(timespec="seconds")
    if not text:
        return SearchOutcome(query="", engine=engine, error="검색어 없음", fetched_at=stamp)

    key = (api_key or "").strip()
    if not key:
        try:
            from iris.infrastructure.api_quota import _env_get

            key = _env_get("SERPAPI_API_KEY", "SERPAPI_KEY")
        except Exception:  # noqa: BLE001
            key = ""
    if not key:
        key = (os.environ.get("SERPAPI_API_KEY") or "").strip()
    if not key:
        return SearchOutcome(
            query=text,
            engine=engine,
            error="SerpApi 키가 없습니다 (설정 → 검색 API)",
            fetched_at=stamp,
        )

    try:
        from iris.infrastructure.serpapi_client import search

        payload = search(
            text,
            engine=engine or DEFAULT_ENGINE,
            api_key=key,
            num=max(1, min(int(count or DEFAULT_COUNT), MAX_COUNT)),
            hl=hl,
            gl=gl,
        )
    except Exception as exc:  # noqa: BLE001
        return SearchOutcome(query=text, engine=engine, error=str(exc)[:200], fetched_at=stamp)

    if isinstance(payload, dict) and payload.get("error") and not any(
        payload.get(k) for k in _RESULT_KEYS
    ):
        return SearchOutcome(
            query=text, engine=engine, error=str(payload["error"])[:200], fetched_at=stamp
        )

    hits = parse_results(payload if isinstance(payload, dict) else {}, limit=count)
    if not hits:
        return SearchOutcome(
            query=text, engine=engine, error="검색 결과 없음", fetched_at=stamp
        )
    return SearchOutcome(hits=hits, query=text, engine=engine, fetched_at=stamp)


def format_evidence(outcome: SearchOutcome) -> str:
    """모델에 넣을 근거 블록. 실패했으면 **그 사실을** 넣는다.

    실패를 조용히 빈 문자열로 만들면 모델은 검색이 없었던 줄 알고 지어낸다.
    """
    if outcome.error:
        return "\n".join(
            [
                "# 웹 검색 결과",
                "",
                "상태: 실패",
                f"오류: {outcome.error}",
                f"검색어: {outcome.query or '(없음)'}",
            ]
        )
    lines = [
        "# 웹 검색 결과",
        "",
        f"검색어: {outcome.query} · {outcome.fetched_at} 기준 · {len(outcome.hits)}건",
    ]
    if not any(hit.snippet for hit in outcome.hits):
        lines.append("본문 요약 없음. 제목만 있다.")
    lines.append("")
    lines.extend(hit.as_line() for hit in outcome.hits)
    return "\n".join(lines)


if __name__ == "__main__":
    payload = {
        "news_results": [
            {
                "title": "오늘의 주요뉴스",
                "link": "https://example.com/a",
                "source": {"name": "JTBC"},
                "date": "09/29/2026, 10:43 PM",
                "snippet": "요약문",
            },
            {"title": "두 번째", "source": "연합뉴스"},
            {"no_title": "버려짐"},
        ]
    }
    hits = parse_results(payload)
    assert len(hits) == 2
    assert hits[0].title == "오늘의 주요뉴스" and hits[0].source == "JTBC"
    assert hits[1].source == "연합뉴스" and hits[1].link == ""
    assert parse_results({"organic_results": [{"title": "웹"}]})[0].title == "웹"
    assert parse_results({}) == []
    assert len(parse_results(payload, limit=1)) == 1

    line = hits[0].as_line()
    assert "오늘의 주요뉴스" in line and "JTBC" in line and "https://example.com/a" in line

    ok = SearchOutcome(hits=hits, query="주요 뉴스", fetched_at="2026-09-29T09:00:00")
    assert ok.ok is True
    block = format_evidence(ok)
    assert "웹 검색 결과" in block and "2건" in block
    assert "덧붙이지 마라" not in block
    assert "JTBC" in block
    assert "본문 요약 없음" not in block

    titles_only = SearchOutcome(
        hits=[SearchHit(title="반도체주 급락"), SearchHit(title="환율 상승")],
        query="경제",
        fetched_at="2026-09-29T09:00:00",
    )
    assert "본문 요약 없음" in format_evidence(titles_only)

    bad = SearchOutcome(query="주요 뉴스", error="SerpApi 키가 없습니다")
    assert bad.ok is False
    fail_block = format_evidence(bad)
    assert "상태: 실패" in fail_block
    assert "SerpApi 키가 없습니다" in fail_block
    assert "지어내지 말고" not in fail_block

    # 네트워크 없이 확인할 수 있는 것만 여기서 본다 — 실제 검색은 테스트에서 모킹한다.
    assert run_search("").error == "검색어 없음"
    assert run_search("   ").error == "검색어 없음"

    print("routine_search self-check ok")
