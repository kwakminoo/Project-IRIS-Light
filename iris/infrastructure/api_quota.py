"""외부 API 월 할당량(검색·크레딧) 조회.

Hermes `%LOCALAPPDATA%/hermes/.env` 키를 읽어 SerpApi·Firecrawl 잔량을 가져온다.
Exa/Naver/Gemini는 공개 잔량 API가 없어 제외.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SERPAPI_ACCOUNT = "https://serpapi.com/account.json"
_FIRECRAWL_USAGE_URLS = (
    "https://api.firecrawl.dev/v2/team/credit-usage",
    "https://api.firecrawl.dev/v1/team/credit-usage",
)


@dataclass(frozen=True)
class ApiQuota:
    """단일 API 할당량 스냅샷."""

    key: str  # serp | fire | sess | week
    label: str
    used: float
    total: float

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * float(self.used) / float(self.total)))


def _hermes_env_path() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or ""
    if local:
        return Path(local) / "hermes" / ".env"
    return Path.home() / ".hermes" / ".env"


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        key = k.strip()
        val = v.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def _env_get(*names: str) -> str:
    """프로세스 env → Hermes .env 순으로 키 조회."""
    for name in names:
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    hermes = _parse_dotenv(_hermes_env_path())
    for name in names:
        v = (hermes.get(name) or "").strip()
        if v:
            return v
    return ""


def _get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 12.0) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "iris-light-quota/1.0", **(headers or {})}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                data.setdefault("error", f"HTTP {exc.code}")
                return data
        except json.JSONDecodeError:
            pass
        return {"error": f"HTTP {exc.code}", "body": body[:300]}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}


def fetch_serpapi_quota(api_key: str | None = None) -> ApiQuota | None:
    key = (api_key or _env_get("SERPAPI_API_KEY", "SERPAPI_KEY")).strip()
    if not key:
        return None
    data = _get_json(f"{_SERPAPI_ACCOUNT}?{urlencode({'api_key': key})}")
    if "error" in data and "searches_per_month" not in data:
        return None
    total = int(data.get("searches_per_month") or 0)
    used = int(data.get("this_month_usage") or 0)
    if total <= 0:
        left = int(data.get("total_searches_left") or data.get("plan_searches_left") or 0)
        total = used + left
    if total <= 0:
        return None
    return ApiQuota(key="serp", label="SERP", used=max(0, used), total=total)


def fetch_firecrawl_quota(api_key: str | None = None) -> ApiQuota | None:
    key = (api_key or _env_get("FIRECRAWL_API_KEY")).strip()
    if not key:
        return None
    data: dict[str, Any] = {}
    for url in _FIRECRAWL_USAGE_URLS:
        data = _get_json(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        if data.get("success") or "data" in data:
            break
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return None
    remaining = payload.get("remainingCredits", payload.get("remaining_credits"))
    plan = payload.get("planCredits", payload.get("plan_credits"))
    if remaining is None:
        return None
    rem = int(remaining)
    total = int(plan) if plan is not None else max(rem, 0)
    if total <= 0 and rem >= 0:
        # ponytail: free plan planCredits 누락 시 remaining만 보이는 경우 — 상한을 rem으로 두면 사용량 0
        total = rem
        used = 0
    else:
        used = max(0, total - rem)
    if total <= 0:
        return None
    return ApiQuota(key="fire", label="FIRE", used=used, total=total)


def fetch_api_quotas() -> list[ApiQuota]:
    """설정된 키만 조회. 실패·미설정은 목록에서 제외."""
    out: list[ApiQuota] = []
    for fetch in (fetch_serpapi_quota, fetch_firecrawl_quota):
        try:
            q = fetch()
        except Exception:
            q = None
        if q is not None:
            out.append(q)
    try:
        from iris.infrastructure.ollama_usage import fetch_ollama_quotas

        out.extend(fetch_ollama_quotas())
    except Exception:
        pass
    return out


def format_quota_pair(used: float, total: float) -> str:
    """좁은 HUD용 used/total 표기. Ollama는 한도 100% 기준 사용량 %만."""
    if total <= 0:
        return "-"  # ASCII: cp949 콘솔·좁은 HUD 공통
    # Ollama Cloud 세션/주간은 percent/100 — 사용량만
    if float(total) == 100.0 and 0 <= float(used) <= 100:
        u = float(used)
        if abs(u - round(u)) < 0.05:
            return f"{int(round(u))}%"
        return f"{u:.1f}%"

    def _n(n: float) -> str:
        n = max(0, int(n))
        if n >= 1_000_000:
            v = n / 1_000_000
            return f"{v:.1f}M".replace(".0M", "M")
        if n >= 10_000:
            return f"{n // 1000}k"
        if n >= 1000:
            v = n / 1000
            return f"{v:.1f}k".replace(".0k", "k")
        return str(n)

    return f"{_n(used)}/{_n(total)}"


if __name__ == "__main__":
    assert format_quota_pair(42, 250) == "42/250"
    assert format_quota_pair(24042, 30000) == "24k/30k"
    assert format_quota_pair(12, 100) == "12%"
    assert format_quota_pair(0.2, 100) == "0.2%"
    assert format_quota_pair(0, 0) == "-"
    assert ApiQuota("t", "T", 25, 100).percent == 25.0
    print("api_quota self-check ok")
