"""Ollama/API VLM이 업무 학습에 적합한지 판별."""

from __future__ import annotations

import re
from dataclasses import dataclass

from iris.infrastructure.ollama_client import OllamaClient, OllamaModelInfo

# 학습용으로 알려진 vision 계열 (이름 휴리스틱)
_STRONG_VISION = re.compile(
    r"(llava|bakllava|qwen2\.?5?-?vl|qwen2-vl|qwen-vl|minicpm-v|llama3\.2-vision|"
    r"gemma3|gemma4|mistral-small.*vision|pixtral|internvl|moondream2|"
    r"gpt-4o|gpt-4\.1|claude-3|claude-sonnet|claude-opus|claude-4)",
    re.I,
)
# 너무 약하거나 비비전
_WEAK_OR_NON = re.compile(
    r"(moondream(?!2)|tinyllava|:\s*0\.5b|:1b\b|:1\.5b|:2b\b|phi3?:|nomic-embed|embed)",
    re.I,
)
_MIN_BYTES_STRONG = 2_500_000_000  # ~2.5GB — 작으면 부족 판정 후보


@dataclass(frozen=True)
class VlmVerdict:
    ok: bool
    reason: str
    provider: str  # ollama | openai | anthropic
    model: str
    supports_vision: bool = False


def supports_vision_capability(capabilities: list[str] | None) -> bool:
    caps = {c.lower() for c in (capabilities or [])}
    return "vision" in caps or "image" in caps or "multimodal" in caps


def model_name_suggests_vision(name: str) -> bool:
    n = (name or "").lower()
    if _STRONG_VISION.search(n):
        return True
    if "vision" in n or "-vl" in n or ":vl" in n:
        return True
    return False


def model_supports_vision(client: OllamaClient, runtime_name: str) -> bool:
    data = client.show_model(runtime_name, timeout_sec=12.0)
    if data and supports_vision_capability(data.get("capabilities")):
        return True
    # capabilities 비어 있으면 이름 휴리스틱
    return model_name_suggests_vision(runtime_name)


def is_learning_capable_vision(
    *,
    name: str,
    size: int = 0,
    supports_vision: bool = False,
) -> tuple[bool, str]:
    """(ok, reason)."""
    if not supports_vision and not model_name_suggests_vision(name):
        return False, "비전(VLM) 기능이 없는 모델입니다. 화면 스크린샷을 이해할 수 없습니다."
    if _WEAK_OR_NON.search(name) and not _STRONG_VISION.search(name):
        return False, "모델 규모/계열이 업무 학습(다단계 GUI trace)에 부족합니다."
    if size and size < _MIN_BYTES_STRONG and not _STRONG_VISION.search(name):
        return False, (
            f"모델 크기({size / 1e9:.1f}GB)가 작아 Aloha 학습용 VLM으로 권장되지 않습니다."
        )
    if not supports_vision and model_name_suggests_vision(name):
        # 이름만으로 vision — 허용하되 안내
        return True, "이름상 비전 모델로 보이며 학습에 사용할 수 있습니다."
    return True, "비전 모델이며 업무 학습에 적합합니다."


def evaluate_ollama_model(client: OllamaClient, runtime_name: str) -> VlmVerdict:
    name = (runtime_name or "").strip()
    if not name:
        return VlmVerdict(False, "선택된 Ollama 모델이 없습니다.", "ollama", "")
    data = client.show_model(name, timeout_sec=12.0)
    caps = data.get("capabilities") if data else None
    vision = supports_vision_capability(caps) or model_name_suggests_vision(name)
    size = 0
    try:
        for m in client.list_models():
            if m.name == name:
                size = m.size
                break
    except Exception:
        pass
    ok, reason = is_learning_capable_vision(
        name=name, size=size, supports_vision=vision
    )
    return VlmVerdict(ok, reason, "ollama", name, supports_vision=vision)


def list_learning_vlm_models(client: OllamaClient) -> list[tuple[OllamaModelInfo, str]]:
    """학습 가능한 Ollama VLM 목록 + 짧은 사유."""
    out: list[tuple[OllamaModelInfo, str]] = []
    try:
        models = client.list_chat_models(probe_cloud=False)
    except Exception:
        models = []
    for m in models:
        vision = model_supports_vision(client, m.name)
        ok, reason = is_learning_capable_vision(
            name=m.name, size=m.size, supports_vision=vision
        )
        if ok:
            out.append((m, reason))
    return out


def evaluate_api_fallback(provider: str, model: str, *, has_key: bool) -> VlmVerdict:
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    if not has_key:
        return VlmVerdict(False, f"{p or 'API'} 키가 없습니다.", p or "openai", m)
    if p not in {"openai", "anthropic", "claude"}:
        return VlmVerdict(False, "지원하지 않는 API provider입니다.", p, m)
    if p == "claude":
        p = "anthropic"
    if not m:
        m = "gpt-4o" if p == "openai" else "claude-sonnet-4-20250514"
    ok, reason = is_learning_capable_vision(name=m, supports_vision=True)
    return VlmVerdict(ok, reason, p, m, supports_vision=True)
