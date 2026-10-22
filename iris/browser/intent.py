"""High-confidence browser command router — does not depend on model tool-calling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

IntentKind = Literal["play", "pause", "resume", "search", "open"]

_QUESTION = re.compile(
    r"(뭐야|뭔가요|무엇|알려줘|설명해|어때\b|할까|왜\b|how do|what is|why\b)",
    re.I,
)
_PLAY = re.compile(r"(틀어|재생해|플레이해|\bplay\b)", re.I)
_YOUTUBE = re.compile(r"(유튜브|youtube|\byt\b)", re.I)
_MUSIC = re.compile(r"(노래|음악|곡|뮤비|뮤직|song|music|mv)\b", re.I)
_PAUSE = re.compile(
    r"(일시\s*정지하|\bpause\b)|((영상|노래|음악|유튜브|youtube|재생).{0,12}(멈춰|정지))",
    re.I,
)
_RESUME = re.compile(r"((이어서|다시)\s*(재생|틀어)|\bresume\b)", re.I)
_YT_SEARCH = re.compile(
    r"(유튜브|youtube)(?:에서|로)?\s+(.+?)\s*(검색|찾아|search)(해|해줘|해 줘|요)?[!?.]*$",
    re.I,
)
_WEB_SEARCH = re.compile(
    r"(구글|google)(?:에서|로)?\s+(.+?)\s*(검색|찾아|search)(해|해줘|해 줘|요)?[!?.]*$",
    re.I,
)
_OPEN_SITE = re.compile(
    r"(네이버|구글|유튜브|youtube|google|naver)(?:을|를)?\s*(열어|켜|들어가)(줘|라|요)?[!?.]*$",
    re.I,
)
_FILLER = {
    "노래",
    "음악",
    "곡",
    "영상",
    "비디오",
    "하나",
    "아무거나",
    "아무나",
    "아무",
    "랜덤",
    "랜덤으로",
    "좀",
    "제발",
    "please",
    "song",
    "music",
    "video",
    "에서",
    "로",
}
_SITES = {
    "네이버": "https://www.naver.com",
    "naver": "https://www.naver.com",
    "구글": "https://www.google.com",
    "google": "https://www.google.com",
    "유튜브": "https://www.youtube.com",
    "youtube": "https://www.youtube.com",
}


@dataclass(frozen=True)
class BrowserIntent:
    control: str
    args: dict[str, Any]
    kind: IntentKind
    query: str = ""


def match_browser_intent(text: str) -> BrowserIntent | None:
    raw = (text or "").strip()
    if not raw or _QUESTION.search(raw):
        return None
    norm = re.sub(r"\s+", " ", raw).strip()

    if _PAUSE.search(norm):
        return BrowserIntent("browser.media", {"action": "pause"}, "pause")
    if _RESUME.search(norm):
        return BrowserIntent("browser.media", {"action": "resume"}, "resume")

    if _PLAY.search(norm):
        query = _extract_play_query(norm)
        if _YOUTUBE.search(norm) or _MUSIC.search(norm) or len(query) >= 2:
            if not query:
                query = "음악"
            return BrowserIntent(
                "browser.search",
                {"query": query, "engine": "youtube", "play": True},
                "play",
                query,
            )
        return None

    yt = _YT_SEARCH.search(norm)
    if yt:
        query = _clean_query(yt.group(2))
        if query:
            return BrowserIntent(
                "browser.search",
                {"query": query, "engine": "youtube"},
                "search",
                query,
            )
    web = _WEB_SEARCH.search(norm)
    if web:
        query = _clean_query(web.group(2))
        if query:
            return BrowserIntent(
                "browser.search",
                {"query": query, "engine": "google"},
                "search",
                query,
            )

    opened = _OPEN_SITE.search(norm)
    if opened:
        url = _SITES.get(opened.group(1).lower()) or _SITES.get(opened.group(1))
        if url:
            return BrowserIntent("browser.navigate", {"url": url}, "open", url)
    return None


def _extract_play_query(norm: str) -> str:
    text = _YOUTUBE.sub(" ", norm)
    text = re.sub(r"(에서|로)\s+", " ", text)
    text = _PLAY.sub(" ", text)
    text = re.sub(r"(줘|라|요|주세요|one|any|random)\b", " ", text, flags=re.I)
    text = re.sub(r"(하나|아무거나|아무나|랜덤으로|좀|제발)", " ", text)
    text = re.sub(r"[!?.]+$", "", text)
    return _clean_query(text)


def _clean_query(text: str) -> str:
    parts = [p for p in re.sub(r"\s+", " ", text).strip().split() if p.lower() not in _FILLER]
    return " ".join(parts).strip(" -")


def format_browser_reply(intent: BrowserIntent, invoked: dict[str, Any]) -> str:
    result = invoked.get("result") if isinstance(invoked.get("result"), dict) else {}
    ok = bool(invoked.get("ok"))
    url = str(result.get("url") or result.get("browser_url") or "")
    title = str(result.get("title") or result.get("browser_title") or "").strip()
    detail = str(result.get("detail") or invoked.get("error") or "").strip()
    media = result.get("media") if isinstance(result.get("media"), dict) else {}
    playing = bool(result.get("browser_playing") or media.get("playing"))
    ad = bool(media.get("ad"))
    block = str(result.get("browser_media_block") or media.get("block") or "")

    if intent.kind == "play":
        if playing and ad:
            return (
                f"광고가 재생 중입니다. 본편 시작은 아직 확인하지 못했습니다."
                f"{_title_bit(title)}"
            )
        if playing:
            return f"유튜브에서 재생을 시작했습니다.{_title_bit(title)} 스피커 출력까지는 확인하지 않습니다."
        reason = _block_text(block) or detail or "재생 상태를 확인하지 못했습니다."
        return f"유튜브 재생을 끝내지 못했습니다. {reason}"
    if intent.kind == "pause":
        if ok and not playing:
            return f"영상을 일시정지했습니다.{_title_bit(title)}"
        return f"일시정지하지 못했습니다. {detail or '재생 중인 영상을 찾지 못했습니다.'}"
    if intent.kind == "resume":
        if playing:
            return f"재생을 다시 시작했습니다.{_title_bit(title)}"
        return f"다시 재생하지 못했습니다. {detail or '영상을 찾지 못했습니다.'}"
    if intent.kind == "search":
        if ok:
            return f"검색했습니다.{_title_bit(title) or (' ' + url if url else '')}"
        return f"검색하지 못했습니다. {detail or '페이지를 열지 못했습니다.'}"
    if ok:
        return f"페이지를 열었습니다.{_title_bit(title) or (' ' + url if url else '')}"
    return f"페이지를 열지 못했습니다. {detail or '브라우저에 연결하지 못했습니다.'}"


def _title_bit(title: str) -> str:
    clean = title.replace("\n", " ").strip()
    if not clean:
        return ""
    return f" ({clean[:80]})"


def _block_text(block: str) -> str:
    return {
        "consent": "동의 화면이 막았습니다. 브라우저에서 동의한 뒤 다시 요청해 주세요.",
        "signin": "로그인이 필요합니다. 내장 브라우저에서 로그인한 뒤 다시 요청해 주세요.",
        "age": "연령 제한으로 재생할 수 없습니다. 우회하지 않습니다.",
        "captcha": "로봇 확인 화면이 나왔습니다. 우회하지 않습니다.",
        "autoplay": "자동재생이 차단되었습니다. 브라우저에서 재생을 눌러 주세요.",
        "no_video": "영상 요소를 찾지 못했습니다.",
        "network": "네트워크 오류로 페이지를 열지 못했습니다.",
    }.get(block, "")
