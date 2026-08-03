"""지도 장소 검색 — Nominatim(무료) + 카카오/네이버/구글맵 열기."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class MapPlace:
    name: str
    address: str
    lat: float
    lon: float

    @property
    def label(self) -> str:
        if self.address and self.address != self.name:
            return f"{self.name} — {self.address}"
        return self.name or self.address


def search_places(query: str, *, limit: int = 8) -> list[MapPlace]:
    q = (query or "").strip()
    if not q:
        return []
    params = urllib.parse.urlencode(
        {
            "q": q,
            "format": "json",
            "addressdetails": "1",
            "limit": str(limit),
            "countrycodes": "kr",
        }
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "IrisLight/1.0 (calendar place picker)",
            "Accept": "application/json",
            "Accept-Language": "ko",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return []
    if not isinstance(data, list):
        return []
    out: list[MapPlace] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        name = str(item.get("name") or "").strip()
        display = str(item.get("display_name") or "").strip()
        if not name:
            name = display.split(",")[0].strip() if display else f"{lat:.5f},{lon:.5f}"
        out.append(MapPlace(name=name, address=display, lat=lat, lon=lon))
    return out


def kakao_map_url(place: MapPlace) -> str:
    q = urllib.parse.quote(place.label)
    return f"https://map.kakao.com/?q={q}"


def naver_map_url(place: MapPlace) -> str:
    q = urllib.parse.quote(place.label)
    return f"https://map.naver.com/v5/search/{q}"


def google_map_url(place: MapPlace) -> str:
    return (
        "https://www.google.com/maps/search/?api=1&query="
        + urllib.parse.quote(f"{place.lat},{place.lon}({place.name})")
    )


if __name__ == "__main__":
    p = MapPlace("테스트", "서울", 37.5, 127.0)
    assert "kakao.com" in kakao_map_url(p)
    assert "naver.com" in naver_map_url(p)
    assert "google.com" in google_map_url(p)
    print("map_place_search ok")
