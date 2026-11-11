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


def model_is_gone(detail: str) -> bool:
    """본문이 모델 부재·비채팅일 때만 True.

    options·max_tokens·unsupported parameter 같은 요청 형식 400은 모델이 죽은 게 아니다.
    """
    text = (detail or "").lower()
    needles = (
        "embedding",
        "not a chat",
        "does not support chat",
        "doesn't support chat",
        "not found",
        "does not exist",
        "doesn't exist",
        "no longer available",
        "unknown model",
        "model_not_found",
        "invalid model",
    )
    return any(n in text for n in needles)


def state_from_http(status: int, detail: str = "") -> str:
    """401/403/429/5xx·형식 400은 미확정(목록 유지). 404/410·비채팅 본문만 제외."""
    if status in (401, 403, 429) or status == 0 or status >= 500:
        return "unverified"
    if status in (404, 410) or model_is_gone(detail):
        return "unavailable"
    if status in (400, 422):
        return "unverified"
    return "unavailable"


def chat_error_hides_model(err: str) -> bool:
    """실제 채팅 실패가 모델을 목록에서 뺄 사유인지.

    Hermes options 400·파라미터 거부는 숨기지 않는다.
    """
    text = err or ""
    if "HTTP 404" in text or "HTTP 410" in text or model_is_gone(text):
        return True
    return False


def should_skip_api_model_verify(state: str, tool_support: str) -> bool:
    if state == "unavailable":
        return True
    if state == "ok" and tool_support in ("yes", "no"):
        return True
    return False


def verify_model(
    base_url: str,
    api_key: str,
    model: str,
    *,
    auth_style: str = "bearer",
    timeout: float = 20.0,
) -> tuple[str, str, str]:
    """(model_state, tool_support, detail). tools 실은 1토큰 요청 1회로 판정함.

    400/422는 도구 거부인지 모델 부재인지 본문만으로 안 갈리므로, 도구 없이 한 번 더 보낸다.
    """
    try:
        oai.chat_smoke(
            base_url, api_key, model, auth_style=auth_style, tools=True, timeout=timeout
        )
        return "ok", "yes", "tools 200"
    except oai.HttpFail as exc:
        if exc.status in (400, 422):
            try:
                oai.chat_smoke(
                    base_url, api_key, model, auth_style=auth_style, timeout=timeout
                )
            except oai.HttpFail as plain:
                return state_from_http(plain.status, plain.detail), "unknown", str(plain)
            tool = "no" if _mentions_tools(exc.detail) else "unknown"
            return "ok", tool, f"tools 없이 대화 가능: {exc.detail[:120]}"
        return state_from_http(exc.status, exc.detail), "unknown", str(exc)


def tool_support_label(state: str) -> str:
    return {"yes": "도구 가능", "no": "도구 미지원"}.get(state, "도구 미확인")


if __name__ == "__main__":
    assert tool_support_from_listing({"supported_parameters": ["tools", "temperature"]}) == "yes"
    assert tool_support_from_listing({"supported_parameters": ["temperature"]}) == "no"
    assert tool_support_from_listing({"supports_tools": True}) == "yes"
    assert tool_support_from_listing({"id": "x"}) == "unknown"
    assert tool_support_from_listing(None) == "unknown"
    assert state_from_http(404, "") == "unavailable"
    assert state_from_http(410, "") == "unavailable"
    assert (
        state_from_http(410, "end of life and no longer available") == "unavailable"
    )
    assert state_from_http(429, "rate limit") == "unverified"
    assert state_from_http(0, "") == "unverified"
    assert state_from_http(503, "overloaded") == "unverified"
    assert state_from_http(400, "Unsupported parameter(s): options") == "unverified"
    assert state_from_http(400, "input must be text embedding") == "unavailable"
    assert chat_error_hides_model("Hermes: HTTP 400 Unsupported parameter(s): options") is False
    assert chat_error_hides_model("HTTP 404 model not found") is True
    assert chat_error_hides_model(
        "HTTP 410: The model is end of life and no longer available."
    )
    assert should_skip_api_model_verify("unavailable", "unknown") is True
    assert should_skip_api_model_verify("", "unknown") is False
    assert should_skip_api_model_verify("ok", "yes") is True
    assert should_skip_api_model_verify("ok", "unknown") is False
    assert _mentions_tools('{"error":"Function calling is not enabled"}')
    assert not _mentions_tools('{"error":"quota exceeded"}')
    assert tool_support_label("unknown") == "도구 미확인"
    print("api_model_meta self-check ok")
