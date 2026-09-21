"""커스텀 OpenAI 호환 API 등록 — user_preferences JSON."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from iris.storage.database import Database

API_PROVIDERS_KEY = "api_providers_v1"
STATUS_VALUES = ("unknown", "ok", "partial", "error")

# 설정 화면 콤보를 채우는 편의 목록 — 추정이 아니라 사용자가 고르는 값임.
# 확정값은 언제나 openai_compat_client.resolve_base_url의 프로브 결과임.
BASE_URL_PRESETS: tuple[tuple[str, str], ...] = (
    ("직접 입력", ""),
    ("OpenAI", "https://api.openai.com/v1"),
    ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("Hugging Face Router", "https://router.huggingface.co/v1"),
    ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("Anthropic", "https://api.anthropic.com/v1"),
    ("Groq", "https://api.groq.com/openai/v1"),
    ("Together", "https://api.together.xyz/v1"),
    ("Ollama (로컬)", "http://127.0.0.1:11434/v1"),
    ("LM Studio (로컬)", "http://127.0.0.1:1234/v1"),
)


@dataclass
class ApiProvider:
    id: str = ""
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    models: list[str] = field(default_factory=list)
    status: str = "unknown"  # unknown | ok | partial | error
    last_error: str = ""
    last_checked_at: str = ""
    enabled: bool = True
    auth_style: str = "bearer"  # bearer | x-api-key
    resolved_base_url: str = ""  # 프로브로 확정된 값. 비면 미확정
    model_states: dict[str, str] = field(default_factory=dict)  # ok|unverified|unavailable
    tool_support: dict[str, str] = field(default_factory=dict)  # yes|no|unknown
    probed_at: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if self.status not in STATUS_VALUES:
            self.status = "unknown"
        if self.auth_style not in ("bearer", "x-api-key"):
            self.auth_style = "bearer"
        cleaned: list[str] = []
        for m in self.models or []:
            s = str(m).strip()
            if s and s not in cleaned:
                cleaned.append(s)
        self.models = cleaned


def parse_models_text(text: str) -> list[str]:
    """콤마·줄바꿈 구분 모델 목록."""
    out: list[str] = []
    for part in (text or "").replace(",", "\n").splitlines():
        s = part.strip()
        if s and s not in out:
            out.append(s)
    return out


def mask_api_key(key: str) -> str:
    """표시용 — 앞 4·뒤 4만 남기고 마스킹."""
    k = (key or "").strip()
    if not k:
        return "(키 없음)"
    if len(k) <= 8:
        return "•" * len(k)
    return f"{k[:4]}…{k[-4:]}"


def runtime_model_id(provider_id: str, model: str) -> str:
    return f"api:{provider_id}:{model}"


def parse_runtime_model_id(runtime: str) -> tuple[str, str] | None:
    """api:{provider_id}:{model} → (provider_id, model). model에 ':' 허용."""
    raw = (runtime or "").strip()
    if not raw.startswith("api:"):
        return None
    rest = raw[4:]
    if ":" not in rest:
        return None
    pid, model = rest.split(":", 1)
    pid = pid.strip()
    model = model.strip()
    if not pid or not model:
        return None
    return pid, model


def is_api_runtime_model(runtime: str) -> bool:
    return parse_runtime_model_id(runtime) is not None


def _from_dict(data: dict) -> ApiProvider:
    models_raw = data.get("models") or []
    if isinstance(models_raw, str):
        models = parse_models_text(models_raw)
    elif isinstance(models_raw, list):
        models = [str(m).strip() for m in models_raw if str(m).strip()]
    else:
        models = []
    status = str(data.get("status") or "unknown").strip().lower()
    if status not in STATUS_VALUES:
        status = "unknown"

    def _str_map(key: str) -> dict[str, str]:
        raw = data.get(key)
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if str(k)}

    return ApiProvider(
        id=str(data.get("id") or "").strip() or uuid.uuid4().hex[:12],
        name=str(data.get("name") or "").strip(),
        base_url=str(data.get("base_url") or "").strip().rstrip("/"),
        api_key=str(data.get("api_key") or ""),
        models=models,
        status=status,
        last_error=str(data.get("last_error") or ""),
        last_checked_at=str(data.get("last_checked_at") or ""),
        enabled=bool(data.get("enabled", True)),
        auth_style=str(data.get("auth_style") or "bearer").strip().lower(),
        resolved_base_url=str(data.get("resolved_base_url") or "").strip().rstrip("/"),
        model_states=_str_map("model_states"),
        tool_support=_str_map("tool_support"),
        probed_at=str(data.get("probed_at") or ""),
    )


def load_api_providers(db: Database | None) -> list[ApiProvider]:
    if db is None:
        return []
    raw = db.get_preference(API_PROVIDERS_KEY, "")
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[ApiProvider] = []
    for item in data:
        if isinstance(item, dict):
            out.append(_from_dict(item))
    return out


def save_api_providers(db: Database, providers: list[ApiProvider]) -> None:
    payload = [asdict(p) for p in providers]
    db.set_preference(API_PROVIDERS_KEY, json.dumps(payload, ensure_ascii=False))


def get_api_provider(db: Database | None, provider_id: str) -> ApiProvider | None:
    pid = (provider_id or "").strip()
    if not pid:
        return None
    for p in load_api_providers(db):
        if p.id == pid:
            return p
    return None


def upsert_api_provider(db: Database, provider: ApiProvider) -> ApiProvider:
    items = load_api_providers(db)
    found = False
    for i, p in enumerate(items):
        if p.id == provider.id:
            items[i] = provider
            found = True
            break
    if not found:
        items.append(provider)
    save_api_providers(db, items)
    return provider


def delete_api_provider(db: Database, provider_id: str) -> bool:
    items = load_api_providers(db)
    nxt = [p for p in items if p.id != provider_id]
    if len(nxt) == len(items):
        return False
    save_api_providers(db, nxt)
    return True


def mark_provider_status(
    db: Database,
    provider_id: str,
    *,
    status: str,
    error: str = "",
    models: list[str] | None = None,
    resolved_base_url: str = "",
    auth_style: str = "",
) -> ApiProvider | None:
    p = get_api_provider(db, provider_id)
    if p is None:
        return None
    p.status = status if status in STATUS_VALUES else "error"
    p.last_error = (error or "")[:400]
    p.last_checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolved = (resolved_base_url or "").strip().rstrip("/")
    if resolved:
        # 프로브가 확정한 URL을 런타임 경로에 되써 저장 — 이후 추정 없음
        p.resolved_base_url = resolved
        p.base_url = resolved
        p.probed_at = p.last_checked_at
    if auth_style in ("bearer", "x-api-key"):
        p.auth_style = auth_style
    if models is not None:
        cleaned: list[str] = []
        for m in models:
            s = str(m).strip()
            if s and s not in cleaned:
                cleaned.append(s)
        if cleaned:
            p.models = cleaned
    return upsert_api_provider(db, p)


def record_model_probe(
    db: Database,
    provider_id: str,
    model: str,
    *,
    state: str,
    tool_support: str,
) -> ApiProvider | None:
    """모델 1건의 실측 결과를 캐시함 — 다음부터는 추정 없이 이 값을 씀."""
    p = get_api_provider(db, provider_id)
    m = (model or "").strip()
    if p is None or not m:
        return None
    p.model_states[m] = state if state in ("ok", "unverified", "unavailable") else "unverified"
    p.tool_support[m] = tool_support if tool_support in ("yes", "no") else "unknown"
    p.probed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return upsert_api_provider(db, p)


def usable_models(provider: ApiProvider) -> list[str]:
    """프로브가 4xx로 거부한 모델은 제외 — 미프로브는 그대로 노출함."""
    return [m for m in provider.models if provider.model_states.get(m) != "unavailable"]


def ok_providers_for_picker(db: Database | None) -> list[ApiProvider]:
    return [
        p
        for p in load_api_providers(db)
        if p.enabled and p.status == "ok" and p.base_url and (p.models or True)
    ]


if __name__ == "__main__":
    assert parse_runtime_model_id("api:abc:gpt-4o") == ("abc", "gpt-4o")
    assert parse_runtime_model_id("api:abc:org/model:v1") == ("abc", "org/model:v1")
    assert parse_runtime_model_id("llama3") is None
    assert runtime_model_id("x", "m") == "api:x:m"
    assert parse_models_text("a, b\nc") == ["a", "b", "c"]
    assert mask_api_key("nvapi-abcdefghijklmnop") == "nvap…mnop"
    assert BASE_URL_PRESETS[0] == ("직접 입력", "")
    # 하위호환 — 신규 필드가 없는 기존 저장분
    legacy = _from_dict({"id": "a1", "name": "Old", "base_url": "https://x/v1"})
    assert legacy.auth_style == "bearer"
    assert legacy.resolved_base_url == "" and legacy.probed_at == ""
    assert legacy.model_states == {} and legacy.tool_support == {}
    marked = ApiProvider(
        name="P",
        base_url="https://x/v1",
        models=["good", "dead"],
        model_states={"dead": "unavailable"},
    )
    assert usable_models(marked) == ["good"]
    print("api_providers self-check ok")
