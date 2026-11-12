"""검색·캘린더 외부 API 키 — Iris Agent .env 읽기·저장 + 발급 링크.

검색은 프리셋 여러 개 + 키. Iris Agent가 아는 백엔드는 그중 마지막 연동 항목을
config.yaml web.search_backend 에 반영한다.
캘린더: data.go.kr 특일정보 (IRIS_DATA_GO_KR_SERVICE_KEY)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from iris.config.settings import default_env_path
from iris.infrastructure.iris_agent_credentials import hermes_home, load_hermes_dotenv

SEARCH_PRESET_ENV = "IRIS_SEARCH_PRESET"
SEARCH_ENTRIES_ENV = "IRIS_SEARCH_ENTRIES"


@dataclass(frozen=True)
class SearchPreset:
    id: str
    label: str
    env_key: str
    signup_url: str
    hint: str
    hermes_backend: str = ""
    extra_env: str = ""
    extra_label: str = ""
    recommended: bool = False
    key_optional: bool = False


@dataclass(frozen=True)
class ApiKeyField:
    env_key: str
    label: str
    signup_url: str
    hint: str = ""
    recommended: bool = False


# 무료 티어로 키를 발급받을 수 있는 검색 API.
# hermes_backend 가 있으면 Hermes web.search_backend 로 연결하고, 없으면 키만 저장한다.
SEARCH_PRESETS: tuple[SearchPreset, ...] = (
    SearchPreset("none", "선택", "", "", "프리셋을 고르면 발급 링크와 키 칸이 맞춰집니다."),
    SearchPreset(
        "serpapi",
        "SerpAPI",
        "SERPAPI_API_KEY",
        "https://serpapi.com/manage-api-key",
        "Google 등 SERP. 무료 월 100회. 키만 저장.",
        recommended=True,
    ),
    SearchPreset(
        "brave",
        "Brave Search",
        "BRAVE_SEARCH_API_KEY",
        "https://api-dashboard.search.brave.com/app/keys",
        "무료 월 2,000회. Iris Agent 웹검색에 연결.",
        hermes_backend="brave-free",
    ),
    SearchPreset(
        "tavily",
        "Tavily",
        "TAVILY_API_KEY",
        "https://app.tavily.com/home",
        "무료 월 1,000 크레딧. Iris Agent 웹검색에 연결.",
        hermes_backend="tavily",
    ),
    SearchPreset(
        "exa",
        "Exa",
        "EXA_API_KEY",
        "https://dashboard.exa.ai/api-keys",
        "시맨틱 검색·본문 추출. 무료 티어. Iris Agent 웹검색에 연결.",
        hermes_backend="exa",
    ),
    SearchPreset(
        "firecrawl",
        "Firecrawl",
        "FIRECRAWL_API_KEY",
        "https://www.firecrawl.dev/app/api-keys",
        "검색·스크랩. 무료 크레딧. Iris Agent 웹검색에 연결.",
        hermes_backend="firecrawl",
    ),
    SearchPreset(
        "parallel",
        "Parallel",
        "PARALLEL_API_KEY",
        "https://platform.parallel.ai/",
        "검색·페이지 추출. 무료 티어. Iris Agent 웹검색에 연결.",
        hermes_backend="parallel",
    ),
    SearchPreset(
        "keenable",
        "Keenable",
        "KEENABLE_API_KEY",
        "https://keenable.ai",
        "검색·페이지 fetch. 무료 티어. Iris Agent 웹검색에 연결.",
        hermes_backend="keenable",
        key_optional=True,
    ),
    SearchPreset(
        "ddgs",
        "DuckDuckGo",
        "",
        "",
        "키 없이 사용. Iris Agent 웹검색에 연결.",
        hermes_backend="ddgs",
        key_optional=True,
    ),
    SearchPreset(
        "searxng",
        "SearXNG",
        "SEARXNG_URL",
        "https://docs.searxng.org/",
        "자체 호스트. 키 칸에 인스턴스 URL. Iris Agent 웹검색에 연결.",
        hermes_backend="searxng",
    ),
    SearchPreset(
        "naver",
        "네이버 검색",
        "NAVER_CLIENT_ID",
        "https://developers.naver.com/apps/#/register",
        "검색 Open API. Client ID와 Secret. 키만 저장.",
        extra_env="NAVER_CLIENT_SECRET",
        extra_label="Client Secret",
    ),
    SearchPreset(
        "kakao",
        "카카오 검색",
        "KAKAO_REST_API_KEY",
        "https://developers.kakao.com/console/app",
        "Daum 검색 REST 키. 무료 쿼터. 키만 저장.",
    ),
    SearchPreset(
        "google_cse",
        "Google Programmable Search",
        "GOOGLE_API_KEY",
        "https://programmablesearchengine.google.com/controlpanel/create",
        "무료 일 100회. API 키와 검색엔진 ID(cx). 키만 저장.",
        extra_env="GOOGLE_CSE_ID",
        extra_label="검색엔진 ID (cx)",
    ),
    SearchPreset(
        "serper",
        "Serper",
        "SERPER_API_KEY",
        "https://serper.dev/api-key",
        "Google SERP. 가입 시 2,500회. 키만 저장.",
    ),
    SearchPreset(
        "searchapi",
        "SearchAPI.io",
        "SEARCHAPI_API_KEY",
        "https://www.searchapi.io/users/sign_up",
        "무료 월 100회. 키만 저장.",
    ),
    SearchPreset(
        "jina",
        "Jina Search",
        "JINA_API_KEY",
        "https://jina.ai/api-dashboard",
        "s.jina.ai 검색. 무료 키. 키만 저장.",
    ),
    SearchPreset(
        "mojeek",
        "Mojeek",
        "MOJEEK_API_KEY",
        "https://www.mojeek.com/services/search/web-search-api/",
        "독립 웹 인덱스. 무료 키. 키만 저장.",
    ),
    SearchPreset(
        "linkup",
        "Linkup",
        "LINKUP_API_KEY",
        "https://app.linkup.so/",
        "웹 검색 API. 무료 티어. 키만 저장.",
    ),
    SearchPreset(
        "valueserp",
        "ValueSERP",
        "VALUESERP_API_KEY",
        "https://www.valueserp.com/users/sign_up",
        "무료 월 100회. 키만 저장.",
    ),
    SearchPreset(
        "serpstack",
        "serpstack",
        "SERPSTACK_ACCESS_KEY",
        "https://serpstack.com/signup/free",
        "무료 월 100회. 키만 저장.",
    ),
)

CALENDAR_API_FIELD = ApiKeyField(
    "IRIS_DATA_GO_KR_SERVICE_KEY",
    "공공데이터포털 (특일정보)",
    "https://www.data.go.kr/data/15012690/openapi.do",
    "대한민국 공휴일 — 한국천문연구원 getRestDeInfo",
    recommended=True,
)

_PRESET_BY_ID = {p.id: p for p in SEARCH_PRESETS}


def search_preset_by_id(preset_id: str) -> SearchPreset:
    return _PRESET_BY_ID.get(preset_id or "", SEARCH_PRESETS[0])


def parse_search_entry_ids(raw: str) -> list[str]:
    ids: list[str] = []
    for part in (raw or "").split(","):
        pid = part.strip()
        if pid in _PRESET_BY_ID and pid != "none" and pid not in ids:
            ids.append(pid)
    return ids


def active_search_preset_id(entry_ids: list[str]) -> str:
    """Iris Agent 웹검색은 백엔드가 하나다. 목록에서 에이전트 연동인 마지막 항목을 쓴다."""
    last_hermes = ""
    last_any = "none"
    for pid in entry_ids:
        preset = search_preset_by_id(pid)
        if preset.id == "none":
            continue
        last_any = preset.id
        if preset.hermes_backend:
            last_hermes = preset.id
    return last_hermes or last_any


def search_env_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for preset in SEARCH_PRESETS:
        for key in (preset.env_key, preset.extra_env):
            if key and key not in keys:
                keys.append(key)
    return tuple(keys)


def upsert_dotenv(path: Path, updates: dict[str, str]) -> None:
    """KEY=value upsert. 값은 로그하지 말 것."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            lines = []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def load_search_api_keys() -> dict[str, str]:
    """Iris Agent .env → 검색 관련 키만."""
    env = load_hermes_dotenv()
    out: dict[str, str] = {}
    for key in search_env_keys():
        out[key] = (env.get(key) or os.environ.get(key) or "").strip()
    return out


def load_search_preset_id() -> str:
    env = load_hermes_dotenv()
    stored = (env.get(SEARCH_PRESET_ENV) or os.environ.get(SEARCH_PRESET_ENV) or "").strip()
    if stored in _PRESET_BY_ID:
        return stored
    saved = load_search_api_keys()
    for preset in SEARCH_PRESETS:
        if preset.env_key and saved.get(preset.env_key):
            return preset.id
    return "none"


def load_search_entries() -> list[str]:
    """등록된 검색 프리셋 id. 목록 키가 없으면 기존 단일 프리셋·저장된 키로 옮긴다."""
    env = load_hermes_dotenv()
    if SEARCH_ENTRIES_ENV in env or SEARCH_ENTRIES_ENV in os.environ:
        raw = (env.get(SEARCH_ENTRIES_ENV) or os.environ.get(SEARCH_ENTRIES_ENV) or "")
        return parse_search_entry_ids(raw)
    saved = load_search_api_keys()
    active = load_search_preset_id()
    ids: list[str] = []
    for preset in SEARCH_PRESETS:
        if preset.id == "none":
            continue
        has_key = bool(preset.env_key and saved.get(preset.env_key))
        if has_key or (preset.key_optional and preset.id == active):
            ids.append(preset.id)
    if not ids and active != "none":
        ids.append(active)
    return ids


def save_search_api_keys(
    values: dict[str, str],
    *,
    preset_id: str = "",
    entry_ids: list[str] | None = None,
) -> Path:
    """검색 키와 선택 프리셋을 Iris Agent .env에 저장하고 프로세스 환경에도 반영."""
    existing = load_hermes_dotenv()
    updates: dict[str, str] = {}
    for key in search_env_keys():
        if key not in values:
            continue
        val = (values.get(key) or "").strip()
        if val or (existing.get(key) or os.environ.get(key) or "").strip():
            updates[key] = val
    pid = (preset_id or values.get(SEARCH_PRESET_ENV) or "").strip()
    if pid in _PRESET_BY_ID:
        updates[SEARCH_PRESET_ENV] = pid
    if entry_ids is not None:
        ids = parse_search_entry_ids(",".join(entry_ids))
        updates[SEARCH_ENTRIES_ENV] = ",".join(ids)
    path = hermes_home() / ".env"
    if updates:
        upsert_dotenv(path, updates)
        for key, val in updates.items():
            if val:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
    return path


def apply_hermes_search_backend(backend: str, *, config_path: Path | None = None) -> None:
    """config.yaml 최상위 web.search_backend / web.backend 만 바꾼다.

    파일 전체를 dump하면 PATH 같은 기존 값이 깨지므로 해당 줄만 고친다.
    """
    backend = (backend or "").strip()
    if not backend or any(c.isspace() for c in backend):
        return
    path = config_path or (hermes_home() / "config.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines()
    web_at = next((i for i, line in enumerate(lines) if line.startswith("web:")), None)
    if web_at is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(["web:", f"  search_backend: {backend}", f"  backend: {backend}"])
    else:
        block_end = len(lines)
        for j in range(web_at + 1, len(lines)):
            if lines[j] and not lines[j].startswith((" ", "#", "\t")):
                block_end = j
                break

        def _set(key: str) -> None:
            nonlocal block_end
            prefix = f"  {key}:"
            for k in range(web_at + 1, block_end):
                if lines[k].startswith(prefix):
                    lines[k] = f"  {key}: {backend}"
                    return
            lines.insert(web_at + 1, f"  {key}: {backend}")
            block_end += 1

        _set("backend")
        _set("search_backend")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_calendar_api_key() -> str:
    return (
        os.environ.get(CALENDAR_API_FIELD.env_key, "").strip()
        or _read_iris_env_key(CALENDAR_API_FIELD.env_key)
    )


def save_calendar_api_key(value: str) -> Path:
    key = (value or "").strip()
    path = default_env_path()
    upsert_dotenv(path, {CALENDAR_API_FIELD.env_key: key})
    if key:
        os.environ[CALENDAR_API_FIELD.env_key] = key
    else:
        os.environ.pop(CALENDAR_API_FIELD.env_key, None)
    return path


def _read_iris_env_key(name: str) -> str:
    path = default_env_path()
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    return ""


def _check_backend_splice() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        cfg.write_text("model:\n  provider: ollama\n", encoding="utf-8")
        apply_hermes_search_backend("tavily", config_path=cfg)
        apply_hermes_search_backend("exa", config_path=cfg)
        apply_hermes_search_backend("", config_path=cfg)
        text = cfg.read_text(encoding="utf-8")
    assert "provider: ollama" in text
    assert text.count("search_backend:") == 1
    assert "search_backend: exa" in text
    assert "backend: exa" in text


if __name__ == "__main__":
    assert SEARCH_PRESETS[0].id == "none"
    ids = [p.id for p in SEARCH_PRESETS]
    assert len(ids) == len(set(ids))
    serp = search_preset_by_id("serpapi")
    assert serp.recommended and "serpapi.com" in serp.signup_url
    assert search_preset_by_id("naver").extra_env == "NAVER_CLIENT_SECRET"
    assert search_preset_by_id("ddgs").key_optional and not search_preset_by_id("ddgs").signup_url
    assert "data.go.kr" in CALENDAR_API_FIELD.signup_url
    assert "SERPAPI_API_KEY" in search_env_keys()
    assert parse_search_entry_ids("serpapi, brave, nope, serpapi") == ["serpapi", "brave"]
    assert active_search_preset_id(["serpapi", "brave", "tavily"]) == "tavily"
    assert active_search_preset_id(["brave", "serpapi"]) == "brave"
    assert active_search_preset_id([]) == "none"
    _check_backend_splice()
    print("external_api_keys ok", len(SEARCH_PRESETS))
