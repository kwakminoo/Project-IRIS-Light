"""SerpApi web search provider for Hermes Agent.

Common endpoint: ``https://serpapi.com/search`` (also ``/search.json``).
Engine selection is via the ``engine`` query parameter.

Env::

    SERPAPI_API_KEY=...          # preferred
    SERPAPI_KEY=...              # alias
    SERPAPI_DEFAULT_ENGINE=google  # optional (default google)

Config::

    web:
      search_backend: "serpapi"
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# engine_id → (display name, primary query param)
# Source: SerpApi API Documentation sidebar (2026-07).
ENGINES: Dict[str, Tuple[str, str]] = {
    "google": ("Google Search", "q"),
    "google_light": ("Google Light Search", "q"),
    "google_images": ("Google Images", "q"),
    "google_images_light": ("Google Images Light", "q"),
    "google_news": ("Google News", "q"),
    "google_news_light": ("Google News Light", "q"),
    "google_videos": ("Google Videos", "q"),
    "google_videos_light": ("Google Videos Light", "q"),
    "google_scholar": ("Google Scholar", "q"),
    "google_maps": ("Google Maps", "q"),
    "google_local": ("Google Local", "q"),
    "google_shopping": ("Google Shopping", "q"),
    "google_shopping_light": ("Google Shopping Light", "q"),
    "google_jobs": ("Google Jobs", "q"),
    "google_flights": ("Google Flights", "q"),
    "google_hotels": ("Google Hotels", "q"),
    "google_hotels_autocomplete": ("Google Hotels Autocomplete", "q"),
    "google_finance": ("Google Finance", "q"),
    "google_events": ("Google Events", "q"),
    "google_autocomplete": ("Google Autocomplete", "q"),
    "google_related_questions": ("Google Related Questions", "q"),
    "google_lens": ("Google Lens", "url"),
    "google_reverse_image": ("Google Reverse Image", "image_url"),
    "google_patents": ("Google Patents", "q"),
    "google_trends": ("Google Trends", "q"),
    "google_play": ("Google Play Store", "q"),
    "google_ai_mode": ("Google AI Mode", "q"),
    "google_ai_overview": ("Google AI Overview", "q"),
    "bing": ("Bing Search", "q"),
    "bing_images": ("Bing Images", "q"),
    "bing_news": ("Bing News", "q"),
    "bing_videos": ("Bing Videos", "q"),
    "bing_shopping": ("Bing Shopping", "q"),
    "bing_maps": ("Bing Maps", "q"),
    "yahoo": ("Yahoo! Search", "p"),
    "yahoo_images": ("Yahoo! Images", "p"),
    "yahoo_videos": ("Yahoo! Videos", "p"),
    "duckduckgo": ("DuckDuckGo Search", "q"),
    "duckduckgo_news": ("DuckDuckGo News", "q"),
    "duckduckgo_light": ("DuckDuckGo Light", "q"),
    "duckduckgo_maps": ("DuckDuckGo Maps", "q"),
    "baidu": ("Baidu Search", "q"),
    "baidu_news": ("Baidu News", "q"),
    "yandex": ("Yandex Search", "text"),
    "yandex_images": ("Yandex Images", "text"),
    "yandex_videos": ("Yandex Videos", "text"),
    "youtube": ("YouTube Search", "search_query"),
    "amazon": ("Amazon Search", "k"),
    "ebay": ("eBay Search", "_nkw"),
    "walmart": ("Walmart Search", "query"),
    "home_depot": ("The Home Depot Search", "q"),
    "yelp": ("Yelp Search", "find_desc"),
    "tripadvisor": ("Tripadvisor Search", "q"),
    "naver": ("Naver Search", "query"),
    "apple_app_store": ("Apple App Store", "term"),
    "apple_maps": ("Apple Maps", "q"),
    "facebook_profile": ("Facebook Profile", "profile_id"),
    "instagram_profile": ("Instagram Profile", "username_or_url"),
}


def _api_key() -> str:
    return get_provider_env("SERPAPI_API_KEY") or get_provider_env("SERPAPI_KEY")


def _default_engine() -> str:
    eng = get_provider_env("SERPAPI_DEFAULT_ENGINE") or "google"
    return eng.strip().lower() or "google"


def serpapi_search(
    query: str,
    *,
    engine: Optional[str] = None,
    limit: int = 5,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call SerpApi ``/search.json`` with ``engine`` + query.

    Returns Hermes web_search shape on success for organic-style engines,
    or a richer ``raw`` payload for specialized engines.
    """
    api_key = _api_key()
    if not api_key:
        return {
            "success": False,
            "error": "SERPAPI_API_KEY (or SERPAPI_KEY) is not set",
        }

    eng = (engine or _default_engine()).strip().lower()
    q_param = ENGINES.get(eng, (eng, "q"))[1]
    params: Dict[str, Any] = {
        "engine": eng,
        "api_key": api_key,
        "num": max(1, min(int(limit), 100)),
    }
    if query:
        params[q_param] = query
    if extra:
        params.update(extra)

    url = f"{SERPAPI_ENDPOINT}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "hermes-serpapi/1.0"}, method="GET")
    try:
        with urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return {
            "success": False,
            "error": f"SerpApi HTTP {exc.code}: {body or exc.reason}",
        }
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"success": False, "error": f"SerpApi request failed: {exc}"}

    if data.get("error"):
        return {"success": False, "error": str(data["error"])}

    web = _normalize_results(data, limit=limit)
    return {
        "success": True,
        "data": {"web": web, "engine": eng},
        "search_metadata": data.get("search_metadata"),
    }


def _normalize_results(data: Dict[str, Any], *, limit: int) -> List[Dict[str, Any]]:
    """Map common SerpApi result arrays into Hermes web[] shape."""
    candidates: List[Dict[str, Any]] = []
    for key in (
        "organic_results",
        "news_results",
        "images_results",
        "video_results",
        "shopping_results",
        "local_results",
        "inline_images",
        "organic_results_state",
    ):
        block = data.get(key)
        if isinstance(block, list):
            candidates.extend(block)
        elif isinstance(block, dict) and isinstance(block.get("places"), list):
            candidates.extend(block["places"])

    if not candidates and isinstance(data.get("recipes_results"), list):
        candidates = data["recipes_results"]

    out: List[Dict[str, Any]] = []
    for i, r in enumerate(candidates[:limit]):
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or r.get("name") or r.get("source") or "")
        url = str(
            r.get("link")
            or r.get("url")
            or r.get("product_link")
            or r.get("thumbnail")
            or ""
        )
        desc = str(
            r.get("snippet")
            or r.get("description")
            or r.get("content")
            or r.get("address")
            or ""
        )
        # 채팅 인라인 이미지용 — 직접 이미지 URL이 있으면 설명에 노출
        thumb = str(
            r.get("thumbnail")
            or r.get("original")
            or r.get("image")
            or r.get("serpapi_thumbnail")
            or ""
        ).strip()
        if thumb.startswith("http") and thumb not in desc and thumb != url:
            desc = f"{desc} Image: {thumb}".strip() if desc else f"Image: {thumb}"
        out.append(
            {
                "title": title,
                "url": url,
                "description": desc,
                "position": int(r.get("position") or i + 1),
            }
        )
    return out


class SerpApiWebSearchProvider(WebSearchProvider):
    """SerpApi search backend — ``engine`` param selects Google/Bing/Yahoo/…"""

    @property
    def name(self) -> str:
        return "serpapi"

    @property
    def display_name(self) -> str:
        return "SerpApi"

    def is_available(self) -> bool:
        return bool(_api_key())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        result = serpapi_search(query, engine=_default_engine(), limit=limit)
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "unknown")}
        return {
            "success": True,
            "data": {"web": (result.get("data") or {}).get("web") or []},
        }

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "SerpApi",
            "badge": "api-key",
            "tag": "Multi-engine SERP JSON (Google/Bing/Yahoo/…). Free plan ~250/mo.",
            "env_vars": [
                {
                    "key": "SERPAPI_API_KEY",
                    "prompt": "SerpApi private API key",
                    "url": "https://serpapi.com/manage-api-key",
                },
            ],
        }
