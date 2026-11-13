"""API 모델 listing 설명 → 한국어 UI 블러브 (카탈로그 우선, 번역 fallback)."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from iris.infrastructure.model_descriptions import describe_model

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_CACHE_PATH = Path.home() / ".iris-light" / "cache" / "model_blurb_ko.json"
_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_CACHE_LOCK = threading.Lock()
_cache: dict[str, str] | None = None


def has_hangul(text: str) -> bool:
    """문자열에 한글 음절이 하나라도 있으면 True."""
    return bool(_HANGUL_RE.search(text or ""))


def display_api_description(runtime: str, listing_description: str = "") -> str:
    """런타임·listing 설명 → 피커용 한국어 블러브."""
    catalog = describe_model(runtime)
    if catalog:
        return catalog
    listing = (listing_description or "").strip()
    if not listing:
        return ""
    if has_hangul(listing):
        return listing
    translated = translate_en_to_ko(listing)
    return translated if translated else ""


def translate_en_to_ko(text: str) -> str:
    """영문 listing을 한국어로 번역. 디스크 캐시·실패 시 원문 유지."""
    src = (text or "").strip()
    if not src:
        return ""
    if has_hangul(src):
        return src
    key = _cache_key(src)
    with _CACHE_LOCK:
        cache = _load_cache()
        hit = cache.get(key)
    if hit is not None:
        return hit
    translated = _fetch_mymemory(src)
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[key] = translated
        _save_cache(cache)
    return translated


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    loaded: dict[str, str] = {}
    try:
        if _CACHE_PATH.is_file():
            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                loaded = {str(k): str(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        loaded = {}
    _cache = loaded
    return _cache


def _save_cache(data: dict[str, str]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_CACHE_PATH)
    except OSError:
        pass


def _fetch_mymemory(text: str) -> str:
    q = urllib.parse.quote(text, safe="")
    url = f"{_MYMEMORY_URL}?q={q}&langpair=en|ko"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        chunk = payload.get("responseData")
        if not isinstance(chunk, dict):
            return text
        out = str(chunk.get("translatedText") or "").strip()
        return out or text
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return text
