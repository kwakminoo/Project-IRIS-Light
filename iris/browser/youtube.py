from __future__ import annotations

from urllib.parse import urlparse


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
