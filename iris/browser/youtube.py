from __future__ import annotations

from urllib.parse import quote_plus, urlparse

from iris.browser.types import ByCss, Locator


def youtube_search_url(query: str) -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    return f"https://www.youtube.com/results?search_query={quote_plus(q)}"


def first_watch_locator() -> Locator:
    """YouTube results page — first video title link (no ads/shorts filter)."""
    return ByCss(css="a#video-title")


def page_block_reason(url: str, title: str = "") -> str:
    """Consent / sign-in / age / captcha. Never a bypass hint."""
    low = (url or "").lower()
    head = (title or "").lower()
    if "/sorry/" in low:
        return "captcha"
    if "consent.youtube." in low or "consent.google." in low:
        return "consent"
    if "before you continue" in head or "before you continue" in low:
        return "consent"
    if "accounts.google." in low or "signin/identifier" in low:
        return "signin"
    if "sign in to confirm" in head or "로그인해서 연령" in head:
        return "signin"
    if "age-restricted" in low or "age-restricted" in head or "연령 제한" in head:
        return "age"
    return ""


def is_youtube_watch_url(url: str) -> bool:
    """True for youtube.com/watch… and youtu.be/<id> (and www/m hosts)."""
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host in ("youtu.be", "www.youtu.be"):
        return bool(path.strip("/"))
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        return path == "/watch" or path.startswith("/watch/")
    return False
