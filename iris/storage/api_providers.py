"""커스텀 OpenAI 호환 API 등록 — user_preferences JSON."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from iris.infrastructure.model_roster import (
    RosterEntry,
    SyncResult,
    mark_price_refetch_done,
    needs_price_refetch,
    parse_listing,
    retire_on_http,
    sync_from_listing,
)
from iris.storage.database import Database
from iris.storage.secret_store import decrypt_secret, encrypt_secret

API_PROVIDERS_KEY = "api_providers_v1"
STATUS_VALUES = ("unknown", "ok", "partial", "error")
_AVAILABILITY = ("ok", "unverified", "unavailable", "")
_TOOL_SUPPORT = ("yes", "no", "unknown", "")
_PRICE_CLASS = ("free", "paid", "unknown")
_MODALITY = ("chat", "image", "audio", "video", "embedding", "other", "unknown")

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
    ("Mistral", "https://api.mistral.ai/v1"),
    ("Cerebras", "https://api.cerebras.ai/v1"),
    ("Cloudflare Workers AI", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"),
    ("SambaNova", "https://api.sambanova.ai/v1"),
    ("Cohere", "https://api.cohere.com/compatibility/v1"),
    ("Z.ai (GLM)", "https://api.z.ai/api/paas/v4"),
    ("Alibaba Qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ("SiliconFlow", "https://api.siliconflow.cn/v1"),
    ("ModelScope", "https://api-inference.modelscope.cn/v1"),
    ("Ollama Cloud", "https://ollama.com/v1"),
    ("DeepSeek", "https://api.deepseek.com/v1"),
    ("Together", "https://api.together.xyz/v1"),
    ("Ollama (로컬)", "http://127.0.0.1:11434/v1"),
    ("LM Studio (로컬)", "http://127.0.0.1:1234/v1"),
)


@dataclass(frozen=True)
class FreeLlmOffer:
    """무료 한도 LLM. 한도는 제공자 정책이라 바뀐다. signup_url은 키 발급 페이지."""

    name: str
    limit_note: str
    signup_url: str
    base_url: str


# 2026-09-29 기준. GitHub Models는 2026-07-30 종료라 제외.
# 상시 무료 한도·가입 무료 할당만. 일회성 유료 체험 크레딧(Together 등)은 넣지 않음.
FREE_LLM_OFFERS: tuple[FreeLlmOffer, ...] = (
    FreeLlmOffer(
        "Google Gemini",
        "카드 없이 Flash 무료 · 약 15회/분, 1,500회/일",
        "https://aistudio.google.com/apikey",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    FreeLlmOffer(
        "NVIDIA NIM",
        "개발용 서버리스 무료 · 전화 인증, 모델별 약 40회/분",
        "https://build.nvidia.com/settings/api-keys",
        "https://integrate.api.nvidia.com/v1",
    ),
    FreeLlmOffer(
        "Groq",
        "카드 없이 상시 무료 · 모델별 분당·일일 한도",
        "https://console.groq.com/keys",
        "https://api.groq.com/openai/v1",
    ),
    FreeLlmOffer(
        "OpenRouter",
        "이름 끝이 :free 인 모델 · 분당·일일 상한",
        "https://openrouter.ai/keys",
        "https://openrouter.ai/api/v1",
    ),
    FreeLlmOffer(
        "Mistral",
        "Experiment 무료 한도 · 낮은 초당 호출",
        "https://console.mistral.ai/api-keys",
        "https://api.mistral.ai/v1",
    ),
    FreeLlmOffer(
        "Cerebras",
        "무료 추론 한도 · 모델별 분당·일일 토큰",
        "https://cloud.cerebras.ai/",
        "https://api.cerebras.ai/v1",
    ),
    FreeLlmOffer(
        "Hugging Face",
        "토큰으로 라우터 추론 · 크레딧·속도 제한",
        "https://huggingface.co/settings/tokens",
        "https://router.huggingface.co/v1",
    ),
    FreeLlmOffer(
        "Cloudflare Workers AI",
        "하루 약 1만 뉴런 무료 · Base URL에 계정 ID 필요",
        "https://dash.cloudflare.com/profile/api-tokens",
        "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    ),
    FreeLlmOffer(
        "SambaNova",
        "개발용 무료 호출 · 모델별 약 20회/일",
        "https://cloud.sambanova.ai/",
        "https://api.sambanova.ai/v1",
    ),
    FreeLlmOffer(
        "Cohere",
        "체험 무료 키 · 비상업 한도",
        "https://dashboard.cohere.com/api-keys",
        "https://api.cohere.com/compatibility/v1",
    ),
    FreeLlmOffer(
        "Z.ai (GLM)",
        "Flash 계열 무료 한도 · 동시 1요청",
        "https://z.ai/manage-apikey/apikey-list",
        "https://api.z.ai/api/paas/v4",
    ),
    FreeLlmOffer(
        "Alibaba Qwen",
        "가입 무료 할당 · 모델·지역별, 이후 종량",
        "https://modelstudio.console.alibabacloud.com/",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),
    FreeLlmOffer(
        "SiliconFlow",
        "일부 오픈 모델 무료 한도",
        "https://cloud.siliconflow.cn/account/ak",
        "https://api.siliconflow.cn/v1",
    ),
    FreeLlmOffer(
        "ModelScope",
        "일일 무료 호출 · 모델별 상한",
        "https://modelscope.cn/my/myaccesstoken",
        "https://api-inference.modelscope.cn/v1",
    ),
    FreeLlmOffer(
        "Ollama Cloud",
        "클라우드 무료 한도 · 세션·주간 제한",
        "https://ollama.com/settings/keys",
        "https://ollama.com/v1",
    ),
    FreeLlmOffer(
        "DeepSeek",
        "가입 무료 크레딧 · 소진 후 종량제",
        "https://platform.deepseek.com/api_keys",
        "https://api.deepseek.com/v1",
    ),
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
    # listing roster persist (description/price/modality/retired + round-trip fields)
    model_meta: dict[str, dict] = field(default_factory=dict)

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
        self.model_meta = sanitize_model_meta(self.model_meta)


def preset_index_for_base_url(url: str) -> int:
    """Base URL과 같은 프리셋 칸. 없으면 0(직접 입력)."""
    needle = (url or "").strip().rstrip("/")
    if not needle:
        return 0
    for index, (_label, preset) in enumerate(BASE_URL_PRESETS):
        if (preset or "").rstrip("/") == needle:
            return index
    return 0


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


def empty_model_meta_row() -> dict:
    return {
        "description": "",
        "price_class": "unknown",
        "modality": "unknown",
        "retired": False,
        "retired_at": "",
        "retire_evidence": "",
        "listing_seen_at": "",
        "price_refetch_done": False,
    }


def sanitize_model_meta(raw: object) -> dict[str, dict]:
    """Legacy JSON without model_meta → {}. Invalid rows get defaults."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, value in raw.items():
        mid = str(key).strip()
        if not mid:
            continue
        row = value if isinstance(value, dict) else {}
        price = str(row.get("price_class") or "unknown").strip().lower()
        if price not in _PRICE_CLASS:
            price = "unknown"
        modality = str(row.get("modality") or "unknown").strip().lower()
        if modality not in _MODALITY:
            modality = "unknown"
        out[mid] = {
            "description": str(row.get("description") or ""),
            "price_class": price,
            "modality": modality,
            "retired": bool(row.get("retired", False)),
            "retired_at": str(row.get("retired_at") or ""),
            "retire_evidence": str(row.get("retire_evidence") or ""),
            "listing_seen_at": str(row.get("listing_seen_at") or ""),
            "price_refetch_done": bool(row.get("price_refetch_done", False)),
        }
    return out


def roster_from_provider(provider: ApiProvider) -> list[RosterEntry]:
    """Compose RosterEntry views from models + model_states + tool_support + model_meta."""
    out: list[RosterEntry] = []
    for mid in provider.models:
        meta = provider.model_meta.get(mid) or empty_model_meta_row()
        avail = str(provider.model_states.get(mid) or "unverified")
        if avail not in _AVAILABILITY:
            avail = "unverified"
        tools = str(provider.tool_support.get(mid) or "unknown")
        if tools not in _TOOL_SUPPORT:
            tools = "unknown"
        price = str(meta.get("price_class") or "unknown")
        if price not in _PRICE_CLASS:
            price = "unknown"
        modality = str(meta.get("modality") or "unknown")
        if modality not in _MODALITY:
            modality = "unknown"
        out.append(
            RosterEntry(
                model_id=mid,
                description=str(meta.get("description") or ""),
                price_class=price,  # type: ignore[arg-type]
                modality=modality,  # type: ignore[arg-type]
                availability=avail,  # type: ignore[arg-type]
                tool_support=tools,  # type: ignore[arg-type]
                retired=bool(meta.get("retired", False)),
                retired_at=str(meta.get("retired_at") or ""),
                retire_evidence=str(meta.get("retire_evidence") or ""),
                listing_seen_at=str(meta.get("listing_seen_at") or ""),
                price_refetch_done=bool(meta.get("price_refetch_done", False)),
            )
        )
    return out


def apply_roster_to_provider(
    provider: ApiProvider, entries: Sequence[RosterEntry]
) -> None:
    """Write roster maps onto provider. Never remove ids from models[]."""
    known = set(provider.models)
    for entry in entries:
        mid = (entry.model_id or "").strip()
        if not mid:
            continue
        if mid not in known:
            provider.models.append(mid)
            known.add(mid)
        avail = entry.availability if entry.availability in _AVAILABILITY else "unverified"
        if avail == "":
            avail = "unverified"
        tools = entry.tool_support if entry.tool_support in _TOOL_SUPPORT else "unknown"
        if tools == "":
            tools = "unknown"
        provider.model_states[mid] = avail
        provider.tool_support[mid] = tools
        price = entry.price_class if entry.price_class in _PRICE_CLASS else "unknown"
        modality = entry.modality if entry.modality in _MODALITY else "unknown"
        provider.model_meta[mid] = {
            "description": entry.description or "",
            "price_class": price,
            "modality": modality,
            "retired": bool(entry.retired),
            "retired_at": entry.retired_at or "",
            "retire_evidence": entry.retire_evidence or "",
            "listing_seen_at": entry.listing_seen_at or "",
            "price_refetch_done": bool(entry.price_refetch_done),
        }
    provider.model_meta = sanitize_model_meta(provider.model_meta)


def sync_provider_listing(
    provider: ApiProvider,
    raw_entries: Sequence[Mapping[str, Any] | object],
    *,
    confirm_missing: bool,
    refetch_entries: Callable[[], Sequence[Mapping[str, Any] | object]] | None = None,
    now_iso: str = "",
) -> SyncResult:
    """Merge one brand `/models` listing into provider roster maps.

    Policy and price mid-change (FreeLLMAPI-style, no signed feed) are applied by
    the same brand re-sync on the next probe or refresh that calls this helper with
    a fresh listing. Do not invent a signed catalog.

    Pass confirm_missing=True only when a full `/models` listing succeeded. Partial
    or empty evidence must use confirm_missing=False so rows are not retired.
    Roster ids are never deleted from provider.models[].
    """
    listings = [parse_listing(e) for e in raw_entries]
    listings = [m for m in listings if m.id]
    current = roster_from_provider(provider)
    result = sync_from_listing(
        current,
        listings,
        brand_id=provider.id,
        confirm_missing=confirm_missing,
        now_iso=now_iso,
    )
    if result.needs_price_refetch and refetch_entries is not None:
        try:
            second_raw = list(refetch_entries() or [])
        except Exception:
            second_raw = []
        second = [m for m in (parse_listing(e) for e in second_raw) if m.id]
        # Empty second listing must not confirm_missing-retire the whole brand.
        if second:
            result = sync_from_listing(
                result.entries,
                second,
                brand_id=provider.id,
                confirm_missing=confirm_missing,
                now_iso=now_iso,
            )
        marked = mark_price_refetch_done(result.entries)
        result = SyncResult(
            entries=tuple(marked),
            added=result.added,
            updated=result.updated,
            retired_ids=result.retired_ids,
            needs_price_refetch=needs_price_refetch(marked),
        )
    apply_roster_to_provider(provider, result.entries)
    return result


def retire_provider_on_http(
    provider: ApiProvider,
    model_id: str,
    *,
    status: int = 410,
    evidence: str = "",
    now_iso: str = "",
) -> list[RosterEntry]:
    """Mark a model retired+unavailable on HTTP EOL evidence. Never drop the id."""
    roster = retire_on_http(
        roster_from_provider(provider),
        model_id=model_id,
        status=status,
        evidence=evidence,
        now_iso=now_iso,
    )
    apply_roster_to_provider(provider, roster)
    return roster


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
        api_key=(
            decrypt_secret(str(data.get("api_key_enc") or ""))
            or str(data.get("api_key") or "")
        ),
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
        model_meta=sanitize_model_meta(data.get("model_meta")),
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
    migrate_plaintext = False
    for item in data:
        if isinstance(item, dict):
            out.append(_from_dict(item))
            migrate_plaintext = migrate_plaintext or "api_key" in item
    if migrate_plaintext:
        save_api_providers(db, out)
    return out


def save_api_providers(db: Database, providers: list[ApiProvider]) -> None:
    payload = []
    for provider in providers:
        row = {
            key: value
            for key, value in vars(provider).items()
            if key != "api_key"
        }
        row["api_key_enc"] = encrypt_secret(provider.api_key)
        payload.append(row)
    db.set_preference(API_PROVIDERS_KEY, json.dumps(payload, ensure_ascii=False))


def provider_is_selectable(provider: ApiProvider) -> bool:
    return bool(
        provider.enabled
        and provider.base_url
        and provider.models
        and provider.status in ("ok", "partial")
    )


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
    """피커에 보여줄 모델. 정리에서 거절해도 이름 목록에서 빼지 않는다."""
    return list(provider.models)


def ok_providers_for_picker(db: Database | None) -> list[ApiProvider]:
    """Picker providers use the same ok/partial readiness predicate everywhere."""
    return [p for p in load_api_providers(db) if provider_is_selectable(p)]


if __name__ == "__main__":
    assert parse_runtime_model_id("api:abc:gpt-4o") == ("abc", "gpt-4o")
    assert parse_runtime_model_id("api:abc:org/model:v1") == ("abc", "org/model:v1")
    assert parse_runtime_model_id("llama3") is None
    assert runtime_model_id("x", "m") == "api:x:m"
    assert parse_models_text("a, b\nc") == ["a", "b", "c"]
    assert mask_api_key("nvapi-abcdefghijklmnop") == "nvap…mnop"
    assert BASE_URL_PRESETS[0] == ("직접 입력", "")
    names = [o.name for o in FREE_LLM_OFFERS]
    assert len(names) == len(set(names)) and len(names) >= 10
    assert all(o.signup_url.startswith("https://") and o.base_url.startswith("http") for o in FREE_LLM_OFFERS)
    assert any("nvidia" in o.signup_url for o in FREE_LLM_OFFERS)
    assert any("aistudio.google.com" in o.signup_url for o in FREE_LLM_OFFERS)
    assert all(preset_index_for_base_url(o.base_url) > 0 for o in FREE_LLM_OFFERS)
    gemini = next(o for o in FREE_LLM_OFFERS if "Gemini" in o.name)
    nvidia = next(o for o in FREE_LLM_OFFERS if "NVIDIA" in o.name)
    assert BASE_URL_PRESETS[preset_index_for_base_url(gemini.base_url)][0] == "Google Gemini"
    assert BASE_URL_PRESETS[preset_index_for_base_url(nvidia.base_url)][0] == "NVIDIA NIM"
    # 하위호환 — 신규 필드가 없는 기존 저장분
    legacy = _from_dict({"id": "a1", "name": "Old", "base_url": "https://x/v1"})
    assert legacy.auth_style == "bearer"
    assert legacy.resolved_base_url == "" and legacy.probed_at == ""
    assert legacy.model_states == {} and legacy.tool_support == {}
    assert legacy.model_meta == {}
    marked = ApiProvider(
        name="P",
        base_url="https://x/v1",
        models=["good", "dead"],
        model_states={"dead": "unavailable"},
    )
    assert usable_models(marked) == ["good", "dead"]
    loaded_meta = _from_dict(
        {
            "id": "m1",
            "name": "Meta",
            "base_url": "https://x/v1",
            "models": ["keep-me", "alive"],
            "model_meta": {
                "keep-me": {
                    "description": "Official only",
                    "price_class": "free",
                    "modality": "chat",
                    "retired": True,
                    "retired_at": "2026-11-12T00:00:00Z",
                    "retire_evidence": "listing-missing",
                    "listing_seen_at": "2026-11-01T00:00:00Z",
                    "price_refetch_done": True,
                }
            },
            "model_states": {"keep-me": "unavailable"},
            "tool_support": {"keep-me": "no"},
        }
    )
    assert loaded_meta.model_meta["keep-me"]["description"] == "Official only"
    assert loaded_meta.model_meta["keep-me"]["retired"] is True
    round_trip = roster_from_provider(loaded_meta)
    assert [e.model_id for e in round_trip] == ["keep-me", "alive"]
    assert round_trip[0].retired is True and round_trip[0].price_class == "free"
    apply_roster_to_provider(
        loaded_meta,
        [
            RosterEntry(
                model_id="alive",
                description="Still listed",
                price_class="paid",
                modality="chat",
                availability="ok",
                tool_support="yes",
            )
        ],
    )
    assert "keep-me" in loaded_meta.models
    assert loaded_meta.models == ["keep-me", "alive"]
    assert loaded_meta.model_meta["keep-me"]["retired"] is True
    assert loaded_meta.model_meta["alive"]["price_class"] == "paid"
    print("api_providers self-check ok")
