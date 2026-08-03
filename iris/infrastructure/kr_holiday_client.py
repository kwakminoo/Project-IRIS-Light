"""대한민국 공휴일 — 공공데이터포털 한국천문연구원 특일정보(getRestDeInfo).

인증키: .env 의 IRIS_DATA_GO_KR_SERVICE_KEY
발급: https://www.data.go.kr/data/15012690/openapi.do
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_CACHE_DIR = Path.home() / ".iris-light" / "cache"
_API = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


@dataclass(frozen=True)
class KrHoliday:
    date: str  # YYYY-MM-DD
    name: str
    is_holiday: bool = True


def _cache_path(year: int) -> Path:
    return _CACHE_DIR / f"kr_holidays_{year}.json"


def load_cached_holidays(year: int) -> list[KrHoliday] | None:
    path = _cache_path(year)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list):
        return None
    out: list[KrHoliday] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        name = str(item.get("name") or "").strip()
        if date and name:
            out.append(KrHoliday(date=date, name=name, is_holiday=bool(item.get("is_holiday", True))))
    return out


def save_cached_holidays(year: int, holidays: list[KrHoliday]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = [
        {"date": h.date, "name": h.name, "is_holiday": h.is_holiday} for h in holidays
    ]
    _cache_path(year).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _locdate_to_iso(locdate: object) -> str:
    s = str(locdate or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def fetch_rest_de_holidays(year: int, service_key: str) -> list[KrHoliday]:
    """공휴일 조회. service_key 없으면 ValueError."""
    key = (service_key or "").strip()
    if not key:
        raise ValueError("IRIS_DATA_GO_KR_SERVICE_KEY missing")

    params = urllib.parse.urlencode(
        {
            "solYear": f"{int(year):04d}",
            "numOfRows": "366",
            "_type": "json",
        }
    )
    # ServiceKey는 포털에서 받은 인코딩 그대로 붙인다(재인코딩 금지)
    url = f"{_API}?serviceKey={key}&{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"holiday API HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"holiday API network: {exc.reason}") from exc

    items = (
        body.get("response", {}).get("body", {}).get("items", {}).get("item")
        if isinstance(body, dict)
        else None
    )
    if items is None:
        return []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []

    out: list[KrHoliday] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("dateName") or "").strip()
        date = _locdate_to_iso(item.get("locdate"))
        if not name or not date:
            continue
        is_hol = str(item.get("isHoliday") or "Y").upper() == "Y"
        out.append(KrHoliday(date=date, name=name, is_holiday=is_hol))
    out.sort(key=lambda h: h.date)
    save_cached_holidays(year, out)
    return out


def holidays_for_year(year: int, service_key: str, *, force: bool = False) -> list[KrHoliday]:
    """캐시 우선, 키 있으면 네트워크 갱신."""
    if not force:
        cached = load_cached_holidays(year)
        if cached is not None:
            return cached
    key = (service_key or "").strip()
    if not key:
        return load_cached_holidays(year) or []
    return fetch_rest_de_holidays(year, key)
