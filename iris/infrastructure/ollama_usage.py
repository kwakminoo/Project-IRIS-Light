"""Ollama Cloud 세션·주간 사용량 조회.

공식 잔량 API가 없어 우선순위:
1) ollama.com/settings HTML (세션 쿠키)
2) 로컬 캐시 `%LOCALAPPDATA%/iris-light/ollama_usage.json`
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.infrastructure.api_quota import ApiQuota

_SETTINGS_URL = "https://ollama.com/settings"
# aria-label="Session usage 0.2% used" 또는 "Session usage 4.0%"
_ARIA_RE = re.compile(
    r'aria-label="((?:Session|Weekly) usage)\s+([0-9]+(?:\.[0-9]+)?)\s*%(?:\s*used)?"',
    re.IGNORECASE,
)
# 본문 텍스트: Session usage … 0.2% used
_TEXT_RE = re.compile(
    r"(Session|Weekly)\s+usage[\s\S]{0,160}?([0-9]+(?:\.[0-9]+)?)\s*%\s*used",
    re.IGNORECASE,
)


def _iris_light_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        return Path(local) / "iris-light"
    return Path.home() / ".iris-light"


def usage_cache_path() -> Path:
    return _iris_light_dir() / "ollama_usage.json"


def _cookie_paths() -> list[Path]:
    paths: list[Path] = []
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        paths.append(Path(local) / "iris-light" / "ollama_cookie.txt")
        paths.append(Path(local) / "hermes" / "ollama_cookie.txt")
    paths.append(Path.home() / ".hermes" / "ollama_cookie.txt")
    paths.append(Path.home() / ".iris-light" / "ollama_cookie.txt")
    return paths


def resolve_ollama_cookie() -> str:
    """`__Secure-session=...` 또는 raw session 값."""
    raw = (os.environ.get("OLLAMA_CLOUD_COOKIE") or "").strip()
    if not raw:
        hermes_env = Path(os.environ.get("LOCALAPPDATA") or "") / "hermes" / ".env"
        if hermes_env.is_file():
            try:
                for line in hermes_env.read_text(encoding="utf-8", errors="replace").splitlines():
                    s = line.strip()
                    if s.startswith("OLLAMA_CLOUD_COOKIE="):
                        raw = s.split("=", 1)[1].strip().strip("'").strip('"')
                        break
            except OSError:
                pass
    if not raw:
        for path in _cookie_paths():
            if not path.is_file():
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if raw:
                break
    if not raw:
        return ""
    if "=" not in raw.split(";")[0]:
        return f"__Secure-session={raw}"
    return raw


def write_usage_cache(*, session_pct: float, weekly_pct: float) -> Path:
    """브라우저 등에서 읽은 %를 로컬 캐시에 저장 (Iris HUD 소스)."""
    path = usage_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_pct": float(session_pct),
        "weekly_pct": float(weekly_pct),
        "updated_at": time.time(),
        "source": "ollama.com/settings",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read_usage_cache(*, max_age_sec: float = 7 * 24 * 3600) -> list[ApiQuota]:
    path = usage_cache_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    updated = float(data.get("updated_at") or 0)
    if updated and (time.time() - updated) > max_age_sec:
        return []
    try:
        sess = float(data.get("session_pct"))
        week = float(data.get("weekly_pct"))
    except (TypeError, ValueError):
        return []
    return _pct_quotas(sess, week)


def _pct_quotas(session_pct: float, weekly_pct: float) -> list[ApiQuota]:
    def _one(key: str, label: str, pct: float) -> ApiQuota:
        # used에 소수 % 보존 (format_quota_pair가 소수점 표시)
        used = max(0.0, min(100.0, float(pct)))
        return ApiQuota(key=key, label=label, used=used, total=100)

    return [
        _one("sess", "SESS", session_pct),
        _one("week", "WEEK", weekly_pct),
    ]


def _fetch_settings_html(cookie: str, *, timeout: float = 15.0) -> str:
    req = Request(
        _SETTINGS_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IrisLight/1.0",
            "Accept": "text/html,application/xhtml+xml",
            "Cookie": cookie,
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403, 302):
            return ""
        return body
    except (URLError, TimeoutError, OSError):
        return ""


def parse_usage_html(html: str) -> list[ApiQuota]:
    """settings HTML → SESS/WEEK ApiQuota (used=percent, total=100)."""
    found: dict[str, float] = {}
    text = html or ""
    for label, pct_s in _ARIA_RE.findall(text):
        try:
            pct = float(pct_s)
        except ValueError:
            continue
        key = "sess" if label.lower().startswith("session") else "week"
        found.setdefault(key, pct)
    if len(found) < 2:
        for label, pct_s in _TEXT_RE.findall(text):
            try:
                pct = float(pct_s)
            except ValueError:
                continue
            key = "sess" if label.lower().startswith("session") else "week"
            found.setdefault(key, pct)
    if "sess" not in found and "week" not in found:
        return []
    return _pct_quotas(found.get("sess", 0.0), found.get("week", 0.0))


def fetch_ollama_quotas() -> list[ApiQuota]:
    cookie = resolve_ollama_cookie()
    if cookie:
        html = _fetch_settings_html(cookie)
        if html and ("Session usage" in html or "Weekly usage" in html):
            parsed = parse_usage_html(html)
            if parsed:
                # 쿠키 조회 성공 시 캐시도 갱신
                try:
                    by = {q.key: q.used for q in parsed}
                    write_usage_cache(
                        session_pct=float(by.get("sess", 0)),
                        weekly_pct=float(by.get("week", 0)),
                    )
                except Exception:
                    pass
                return parsed

    cached = read_usage_cache()
    if cached:
        return cached

    # 쿠키 없을 때 오래된 캐시라도 표시 (완전 공란보다 나음)
    stale = read_usage_cache(max_age_sec=30 * 24 * 3600)
    if stale:
        return stale

    # 쿠키·캐시 없으면 로그인 여부만 표시용 플레이스홀더
    if _ollama_signed_in():
        return [
            ApiQuota(key="sess", label="SESS", used=0, total=0),
            ApiQuota(key="week", label="WEEK", used=0, total=0),
        ]
    return []


def _ollama_signed_in() -> bool:
    try:
        req = Request(
            "http://127.0.0.1:11434/api/me",
            data=b"{}",
            headers={"Content-Type": "application/json", "User-Agent": "iris-light-quota/1.0"},
            method="POST",
        )
        with urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(isinstance(data, dict) and data.get("email"))
    except Exception:
        return False


if __name__ == "__main__":
    sample = 'aria-label="Session usage 0.2% used" aria-label="Weekly usage 4.1% used"'
    qs = parse_usage_html(sample)
    assert len(qs) == 2
    assert qs[0].key == "sess" and abs(float(qs[0].used) - 0.2) < 0.01
    assert qs[1].key == "week" and abs(float(qs[1].used) - 4.1) < 0.01
    path = write_usage_cache(session_pct=0.2, weekly_pct=4.1)
    assert read_usage_cache()
    print("ollama_usage self-check ok", path)
