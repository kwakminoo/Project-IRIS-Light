"""커스텀 API(NVIDIA 등) 모델 메타 — 도구·카테고리·장단점 휴리스틱.

ponytail: NVIDIA /models 목록에 capability 필드가 없어 이름 패턴으로 분류.
천장: 새 모델군은 키워드만 추가. 정확 프로브가 필요하면 OpenAI tools 스모크로 업그레이드.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiModelMeta:
    category: str
    supports_tools: bool
    feature: str
    pros: str
    cons: str
    limit: str


# (부분키, 카테고리, tools?, 특징, 장점, 단점, 한도) — 위가 우선
_NVIDIA_RULES: tuple[tuple[str, str, bool, str, str, str, str], ...] = (
    ("flux", "이미지 생성", False, "텍스트→이미지", "고품질 생성", "에이전트/도구 불가", "이미지 전용"),
    ("stable-diffusion", "이미지 생성", False, "SD 계열 생성", "빠른 생성", "도구 불가", "이미지 전용"),
    ("sdxl", "이미지 생성", False, "SDXL 생성", "고해상도", "도구 불가", "이미지 전용"),
    ("imagen", "이미지 생성", False, "이미지 생성", "품질", "도구 불가", "이미지 전용"),
    ("whisper", "음성/TTS", False, "음성→텍스트", "인식 정확", "채팅/도구 불가", "오디오 전용"),
    ("tts", "음성/TTS", False, "텍스트→음성", "자연스러운 음성", "채팅/도구 불가", "오디오 전용"),
    ("riva", "음성/TTS", False, "음성 AI", "실시간성", "채팅 에이전트 부적합", "오디오 전용"),
    ("embed", "임베딩/검색", False, "벡터 임베딩", "검색·RAG", "대화/도구 불가", "임베딩 전용"),
    ("rerank", "임베딩/검색", False, "재순위화", "검색 품질", "대화 불가", "rerank 전용"),
    ("nemotron", "LLM/에이전트", True, "에이전트·도구 추론", "효율·도구", "NIM 쿼터", "채팅+tools"),
    ("llama", "LLM/에이전트", True, "범용 대화·코딩", "생태계·도구", "컨텍스트/쿼터", "채팅+tools"),
    ("qwen", "LLM/에이전트", True, "다국어·코딩", "도구·비전(모델별)", "쿼터", "채팅+tools"),
    ("mistral", "LLM/에이전트", True, "범용·코딩", "빠름·도구", "쿼터", "채팅+tools"),
    ("deepseek", "LLM/에이전트", True, "추론·코딩", "가성비·도구", "쿼터", "채팅+tools"),
    ("gemma", "LLM/에이전트", True, "경량 멀티모달", "로컬친화", "대형 대비 한계", "채팅"),
    ("phi-", "LLM/에이전트", True, "경량 추론", "작음·빠름", "긴 과제 약함", "채팅"),
    ("gpt-oss", "LLM/에이전트", True, "오픈웨이트 추론", "도구·에이전트", "쿼터", "채팅+tools"),
    ("cosmos", "비전/멀티모달", False, "월드/비전 모델", "시각 이해", "일반 채팅 도구 제한", "비전 특화"),
    ("vila", "비전/멀티모달", True, "비전-언어", "이미지+텍스트", "텍스트만 작업엔 과함", "VLM"),
    ("nvclip", "비전/멀티모달", False, "비전 임베딩", "이미지 검색", "대화 불가", "임베딩"),
)

_SINGLE_BRAND_HINTS = ("openai", "gpt", "chatgpt", "anthropic", "claude", "google", "gemini", "gemini")

# ponytail: integrate.api.nvidia.com 무료 Public API에서 chat 스모크 통과한 모델만.
# 천장: NVIDIA가 모델을 열거나 닫으면 목록이 어긋남 → 스모크 재실행 후 이 튜플만 갱신.
_NVIDIA_FREE_ENDPOINT_MODELS: tuple[str, ...] = (
    "google/diffusiongemma-26b-a4b-it",
    "google/gemma-4-31b-it",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "minimaxai/minimax-m3",
    "mistralai/mistral-nemotron",
    "nvidia/ising-calibration-1.5-31b",
    "nvidia/llama-3.1-nemoguard-8b-content-safety",
    "nvidia/llama-3.1-nemoguard-8b-topic-control",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-content-safety",
    "nvidia/nemotron-mini-4b-instruct",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "stepfun-ai/step-3.7-flash",
    "thinkingmachines/inkling",
)
_NVIDIA_FREE_ENDPOINT_SET = frozenset(_NVIDIA_FREE_ENDPOINT_MODELS)


def is_nvidia_provider(name: str, base_url: str = "") -> bool:
    blob = f"{name} {base_url}".lower()
    return "nvidia" in blob or "nim" in blob or "integrate.api.nvidia" in blob


def is_nvidia_free_endpoint_model(model: str) -> bool:
    return (model or "").strip() in _NVIDIA_FREE_ENDPOINT_SET


def filter_nvidia_free_endpoint_models(models: list[str] | None) -> list[str]:
    """피커/저장용 — 무료 엔드포인트 모델만. 교집합이 없으면 무료 목록 전체."""
    seen = {(m or "").strip() for m in (models or []) if (m or "").strip()}
    if not seen:
        return list(_NVIDIA_FREE_ENDPOINT_MODELS)
    hit = [m for m in _NVIDIA_FREE_ENDPOINT_MODELS if m in seen]
    return hit if hit else list(_NVIDIA_FREE_ENDPOINT_MODELS)


def is_multi_model_brand(name: str, base_url: str = "", model_count: int = 0) -> bool:
    """브랜드 하위 모델 선택 창을 쓸지 — NVIDIA 허브 또는 다수 모델."""
    if is_nvidia_provider(name, base_url):
        return True
    if model_count >= 3 and not is_single_brand_provider(name):
        return True
    return False


def is_single_brand_provider(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(h in n for h in _SINGLE_BRAND_HINTS)


def api_model_supports_tools(provider_name: str, model: str, *, base_url: str = "") -> bool:
    return describe_api_model(provider_name, model, base_url=base_url).supports_tools


def nvidia_category(model: str) -> str:
    return describe_api_model("NVIDIA", model).category


def describe_api_model(provider_name: str, model: str, *, base_url: str = "") -> ApiModelMeta:
    m = (model or "").strip().lower()
    nvidia = is_nvidia_provider(provider_name, base_url)
    if nvidia:
        for key, cat, tools, feat, pros, cons, lim in _NVIDIA_RULES:
            if key in m:
                return ApiModelMeta(cat, tools, feat, pros, cons, lim)
        # 기본: NIM chat 계열로 간주 (도구 가능) — 예전처럼 전부 False 고정하지 않음
        return ApiModelMeta(
            "LLM/기타",
            True,
            "OpenAI 호환 채팅",
            "NIM 다양성",
            "모델별 능력 확인 필요",
            "쿼터·엔드포인트",
        )

    # 비-NVIDIA 커스텀 API
    if any(x in m for x in ("embed", "whisper", "tts", "dall-e", "imagen", "flux")):
        return ApiModelMeta("특수", False, "비채팅 모달리티", "특화 작업", "에이전트 부적합", "모달리티 전용")
    # GPT/Claude/Gemini 등 — 도구 지원으로 표시
    return ApiModelMeta(
        "LLM",
        True,
        "대화·에이전트",
        "익숙한 API",
        "키·과금 필요",
        "제공자 한도",
    )


def card_blurb(meta: ApiModelMeta) -> str:
    """MCP 카드 desc 자리에 넣을 한 줄 요약."""
    bits = [
        f"특징 {meta.feature}",
        f"장점 {meta.pros}",
        f"단점 {meta.cons}",
        f"한도 {meta.limit}",
    ]
    if meta.supports_tools:
        bits.append("도구·추론 가능")
    else:
        bits.append("도구 호출 미지원")
    return " · ".join(bits)


if __name__ == "__main__":
    assert api_model_supports_tools("NVIDIA", "meta/llama-3.1-70b-instruct") is True
    assert api_model_supports_tools("NVIDIA", "black-forest-labs/flux.1-dev") is False
    assert api_model_supports_tools("NVIDIA", "nvidia/nv-embedqa-e5-v5") is False
    assert api_model_supports_tools("NVIDIA", "nvidia/nemotron-3-nano") is True
    assert nvidia_category("meta/llama-3.3-70b-instruct") == "LLM/에이전트"
    assert nvidia_category("black-forest-labs/flux.1-dev") == "이미지 생성"
    assert is_nvidia_provider("NVIDIA", "https://integrate.api.nvidia.com/v1")
    assert is_single_brand_provider("OpenAI GPT")
    assert is_nvidia_free_endpoint_model("meta/llama-3.1-8b-instruct")
    assert not is_nvidia_free_endpoint_model("deepseek-ai/deepseek-coder-6.7b-instruct")
    assert filter_nvidia_free_endpoint_models(
        ["deepseek-ai/deepseek-coder-6.7b-instruct", "meta/llama-3.1-8b-instruct"]
    ) == ["meta/llama-3.1-8b-instruct"]
    assert len(filter_nvidia_free_endpoint_models([])) == len(_NVIDIA_FREE_ENDPOINT_MODELS)
    print("api_model_meta self-check ok")
