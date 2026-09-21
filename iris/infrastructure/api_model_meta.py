"""커스텀 API 모델 실측 — 사용가능 여부 + 도구지원 3-상태.

모델·제공자 **이름 문자열로 능력을 추정하지 않음.** 판정 근거는 제공자 `/models`
응답 메타이거나 실제 HTTP 프로브뿐이며, 판정 불가는 `unknown`으로 남김.
"""

from __future__ import annotations

from typing import Any

from iris.infrastructure import openai_compat_client as oai

TOOL_SUPPORT_VALUES = ("yes", "no", "unknown")
MODEL_STATES = ("ok", "unverified", "unavailable")

# 프로브 없이도 정확한 판정 — 인증·과금 없이 목록 응답에서 읽음
_LISTING_TOOL_KEYS = ("supports_tools", "supports_function_calling", "tool_use")


def tool_support_from_listing(entry: dict[str, Any] | None) -> str:
    """`/models` 항목 메타에서 도구지원 판정. 근거 없으면 "unknown"."""
    if not isinstance(entry, dict):
        return "unknown"
    params = entry.get("supported_parameters")
    if isinstance(params, list):  # OpenRouter
        return "yes" if any(str(p).strip() == "tools" for p in params) else "no"
    for key in _LISTING_TOOL_KEYS:  # Hugging Face Router 등
        if key in entry:
            return "yes" if bool(entry[key]) else "no"
    return "unknown"


def _mentions_tools(detail: str) -> bool:
    """제공자가 돌려준 오류 본문에 tool/function 언급이 있는지 — 모델명 추정 아님."""
    text = (detail or "").lower()
    return "tool" in text or "function" in text


def _state_from_status(status: int) -> str:
    # 401/403/429/5xx·네트워크는 모델 탓이 아님 → 미확정으로 남김
    if status in (401, 403, 429) or status == 0 or status >= 500:
        return "unverified"
    return "unavailable"


def verify_model(
    base_url: str,
    api_key: str,
    model: str,
    *,
    auth_style: str = "bearer",
    timeout: float = 20.0,
) -> tuple[str, str, str]:
    """(model_state, tool_support, detail). tools 실은 1토큰 요청 1회로 판정함."""
    try:
        oai.chat_smoke(
            base_url, api_key, model, auth_style=auth_style, tools=True, timeout=timeout
        )
        return "ok", "yes", "tools 200"
    except oai.HttpFail as exc:
        if exc.status in (400, 422) and _mentions_tools(exc.detail):
            # 도구만 거부 — 도구 없이 대화가 되는지 재확인
            try:
                oai.chat_smoke(
                    base_url, api_key, model, auth_style=auth_style, timeout=timeout
                )
                return "ok", "no", f"tools 거부: {exc.detail[:120]}"
            except oai.HttpFail as plain:
                return _state_from_status(plain.status), "unknown", str(plain)
        return _state_from_status(exc.status), "unknown", str(exc)


def tool_support_label(state: str) -> str:
    return {"yes": "도구 가능", "no": "도구 미지원"}.get(state, "도구 미확인")


if __name__ == "__main__":
    assert tool_support_from_listing({"supported_parameters": ["tools", "temperature"]}) == "yes"
    assert tool_support_from_listing({"supported_parameters": ["temperature"]}) == "no"
    assert tool_support_from_listing({"supports_tools": True}) == "yes"
    assert tool_support_from_listing({"id": "x"}) == "unknown"
    assert tool_support_from_listing(None) == "unknown"
    assert _state_from_status(404) == "unavailable"
    assert _state_from_status(429) == "unverified"
    assert _state_from_status(0) == "unverified"
    assert _state_from_status(503) == "unverified"
    assert _mentions_tools('{"error":"Function calling is not enabled"}')
    assert not _mentions_tools('{"error":"quota exceeded"}')
    assert tool_support_label("unknown") == "도구 미확인"
    print("api_model_meta self-check ok")
