"""커스텀 OpenAI 호환 API 등록 — user_preferences JSON."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from iris.storage.database import Database

API_PROVIDERS_KEY = "api_providers_v1"
STATUS_VALUES = ("unknown", "ok", "error")


@dataclass
class ApiProvider:
    id: str = ""
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    models: list[str] = field(default_factory=list)
    status: str = "unknown"  # unknown | ok | error
    last_error: str = ""
    last_checked_at: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if self.status not in STATUS_VALUES:
            self.status = "unknown"
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


def guess_base_url(name: str, base_url: str = "") -> str:
    """Base URL 비었을 때 이름 힌트로 기본 엔드포인트."""
    raw = (base_url or "").strip().rstrip("/")
    if raw:
        return raw
    n = (name or "").strip().lower()
    if "nvidia" in n or "nim" in n:
        return "https://integrate.api.nvidia.com/v1"
    if "openai" in n or n in ("gpt", "chatgpt"):
        return "https://api.openai.com/v1"
    if "anthropic" in n or "claude" in n:
        return "https://api.anthropic.com/v1"
    if "openrouter" in n:
        return "https://openrouter.ai/api/v1"
    return ""


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
) -> ApiProvider | None:
    p = get_api_provider(db, provider_id)
    if p is None:
        return None
    p.status = status if status in STATUS_VALUES else "error"
    p.last_error = (error or "")[:400]
    p.last_checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if models is not None:
        cleaned: list[str] = []
        for m in models:
            s = str(m).strip()
            if s and s not in cleaned:
                cleaned.append(s)
        if cleaned:
            p.models = cleaned
    return upsert_api_provider(db, p)


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
    assert "nvidia.com" in guess_base_url("NVIDIA", "")
    print("api_providers self-check ok")
