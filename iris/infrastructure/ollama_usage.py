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
from iris.infrastructure.hermes_credentials import hermes_home

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
        hermes_env = hermes_home() / ".env"
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


def ollama_cloud_signed_in() -> bool:
    """로컬 Ollama 데몬이 ollama.com 계정으로 로그인돼 있으면 True."""
    return _ollama_signed_in()


def poll_ollama_cloud_signed_in(
    *,
    timeout_sec: float = 180.0,
    interval_sec: float = 2.0,
    check=None,
    sleep=time.sleep,
    stop=None,
) -> bool:
    """앱 로그인 뒤 /api/me 가 True가 될 때까지 기다린다.

    UI 스레드에서 호출하지 말 것. timeout은 로그인 조작 시간(기본 3분).
    """
    check = ollama_cloud_signed_in if check is None else check
    stop = (lambda: False) if stop is None else stop
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    while True:
        if stop():
            return False
        try:
            if check():
                return True
        except Exception:
            pass
        now = time.monotonic()
        if now >= deadline:
            return False
        wait_end = now + min(float(interval_sec), deadline - now)
        while time.monotonic() < wait_end:
            if stop():
                return False
            sleep(min(0.25, wait_end - time.monotonic()))


def ollama_login_status_message(*, applied: bool) -> str:
    """로그인 확인 뒤 채팅에 붙일 한 줄."""
    if applied:
        return (
            "Ollama 클라우드 로그인이 확인되어 Iris에 반영했습니다. "
            "클라우드 모델을 바로 사용할 수 있습니다."
        )
    return (
        "Ollama 로그인은 확인됐지만 이 실행에는 반영되지 않습니다. "
        "Iris를 다시 시작하면 로그인 상태가 적용됩니다."
    )


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
        if not isinstance(data, dict):
            return False
        # 스키마 변동 대비: email / user / username / id + signed_in
        if data.get("email"):
            return True
        if data.get("user") or data.get("username"):
            return True
        if data.get("id") and data.get("signed_in") is not False:
            return True
        if data.get("signed_in") is True or data.get("logged_in") is True:
            return True
        return False
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
    hits = {"n": 0}

    def _later() -> bool:
        hits["n"] += 1
        return hits["n"] >= 3

    assert poll_ollama_cloud_signed_in(
        timeout_sec=5, interval_sec=0, check=_later, sleep=lambda _s: None
    )
    assert (
        poll_ollama_cloud_signed_in(
            timeout_sec=0, interval_sec=0, check=lambda: False, sleep=lambda _s: None
        )
        is False
    )
    assert poll_ollama_cloud_signed_in(
        timeout_sec=5, interval_sec=0, check=lambda: False, sleep=lambda _s: None, stop=lambda: True
    ) is False
    applied = ollama_login_status_message(applied=True)
    restart = ollama_login_status_message(applied=False)
    assert "반영했습니다" in applied and "다시 시작" not in applied
    assert "다시 시작" in restart
    print("ollama_usage self-check ok", path)
