"""Hermes 채팅 오류 분류 — 게이트웨이 Bearer vs Ollama 클라우드 401."""

from __future__ import annotations

import re

# UI·테스트가 안정적으로 잡는 접두 (문구 변경 시 테스트도 같이)
CLOUD_AUTH_ERROR_PREFIX = "Ollama 클라우드 미로그인"
GATEWAY_AUTH_ERROR_PREFIX = "Iris Agent 게이트웨이 API 키"

CLOUD_AUTH_USER_MSG = (
    f"{CLOUD_AUTH_ERROR_PREFIX}입니다. "
    "Ollama 앱에서 로그인하거나 로컬 모델로 바꾸세요."
)
GATEWAY_AUTH_USER_MSG = (
    f"{GATEWAY_AUTH_ERROR_PREFIX} 불일치(HTTP 401). "
    "시작 프로토콜 「다시 설정」으로 API_SERVER_KEY를 맞추세요."
)


def is_cloud_runtime_name(name: str) -> bool:
    from iris.infrastructure.ollama_client import OllamaModelInfo
    from iris.storage.api_providers import is_api_runtime_model

    n = (name or "").strip()
    if not n or is_api_runtime_model(n):
        return False
    return bool(OllamaModelInfo(name=n).is_cloud)


def looks_like_upstream_unauthorized(err_msg: str) -> bool:
    """SSE/업스트림이 올린 401 Unauthorized (게이트웨이 Bearer 문구와 구분)."""
    s = (err_msg or "").strip().lower()
    if not s:
        return False
    if "gateway" in s and "api" in s:
        return False
    if s in ("unauthorized", "http 401: unauthorized", "401 unauthorized"):
        return True
    return "401" in s and "unauthorized" in s


def looks_like_no_tools_error(err_msg: str) -> bool:
    s = (err_msg or "").strip().lower()
    return "does not support tools" in s or "not support tools" in s


def format_hermes_sse_error(err_msg: str, *, model: str = "") -> str:
    """SSE error.message → 사용자용 RuntimeError 본문 (앞에 'Hermes: ' 붙이지 않음)."""
    raw = (err_msg or "").strip()
    if looks_like_upstream_unauthorized(raw):
        if is_cloud_runtime_name(model) or ":cloud" in raw.lower() or "-cloud" in raw.lower():
            return CLOUD_AUTH_USER_MSG
        # 모델명을 모를 때도 클라우드 401과 동일 패턴이면 클라우드 안내 우선
        # (게이트웨이 Bearer 실패는 HTTPError 경로 — 여기로 안 옴)
        try:
            from iris.infrastructure.ollama_usage import ollama_cloud_signed_in

            if not ollama_cloud_signed_in():
                return CLOUD_AUTH_USER_MSG
        except Exception:
            pass
        return CLOUD_AUTH_USER_MSG
    if looks_like_no_tools_error(raw):
        return (
            "이 모델은 도구(tools)를 지원하지 않습니다. "
            "도구 지원 모델을 선택하세요. "
            f"({raw[:120]})"
        )
    return raw


def format_hermes_http_401() -> str:
    """urllib HTTPError 401 — 게이트웨이 Bearer 실패 전용."""
    return GATEWAY_AUTH_USER_MSG


def scrub_upstream_hermes_cli_hints(text: str) -> str:
    """업스트림 format_error 의 `hermes doctor` 등 CLI 힌트를 Iris 안내로 가린다."""
    out = text or ""
    if "hermes doctor" not in out.lower() and "hermes " not in out.lower():
        return out
    out = re.sub(
        r"(?i)\brun\s+[`']?hermes\s+doctor[`']?",
        "Iris 설정·시작 프로토콜을 확인하세요",
        out,
    )
    out = re.sub(r"(?i)\bhermes\s+doctor\b", "Iris Agent 진단", out)
    return out


def explain_chat_error(err: str) -> str:
    """채팅에 보일 안내. 원문 로그는 그대로 두고 화면만 바꾼다.

    할당량 전환(`status_for_error`)은 이 함수 이전의 원문을 본다.
    """
    raw = scrub_upstream_hermes_cli_hints((err or "").strip())
    if not raw:
        return "모델이 응답하지 않았습니다. 다시 시도하세요."
    if CLOUD_AUTH_ERROR_PREFIX in raw or GATEWAY_AUTH_ERROR_PREFIX in raw:
        return raw
    if raw.startswith("이 모델은 도구"):
        return raw
    if raw.startswith("[") and "http" not in raw.lower()[:80]:
        return raw

    from iris.runtime.model_failover import status_for_error

    low = raw.lower()
    status = status_for_error(raw)

    if any(h in low for h in ("연결 실패", "connection refused", "unreachable")):
        return (
            "모델 서버에 연결하지 못했습니다. "
            "Iris Agent 또는 Ollama가 켜져 있는지 확인한 뒤 다시 시도하세요."
        )
    if (
        any(
            h in low
            for h in ("timed out", "timeout", "시간 초과", "시간이 초과")
        )
        or status == 408
        or "엔진 응답을 읽지 못했습니다" in raw
    ):
        return "응답 대기 시간이 초과됐습니다. 잠시 후 다시 시도하세요."
    if looks_like_no_tools_error(raw):
        return "이 모델은 도구 호출을 지원하지 않습니다. 도구를 지원하는 모델을 선택하세요."
    if status == 429 or any(
        h in low for h in ("quota", "exceeded your current", "rate limit", "resource_exhausted")
    ):
        if any(k in low for k in ("gemini", "generativelanguage", "ai.google", "googleapis")):
            return (
                "Gemini API 사용 한도를 초과했습니다. "
                "요금제와 할당량을 확인하거나, 다른 모델로 바꾼 뒤 다시 요청하세요."
            )
        if "ollama" in low:
            return (
                "Ollama 클라우드 사용 한도입니다. "
                "잠시 기다리거나 로컬 모델로 바꾸세요."
            )
        return (
            "모델 API 사용 한도를 초과했습니다. "
            "잠시 후 다시 시도하거나 다른 모델로 바꾸세요."
        )
    if status == 413 or any(
        h in low
        for h in (
            "context length",
            "context_length",
            "maximum context",
            "too many tokens",
            "prompt is too long",
        )
    ):
        return "대화가 모델이 한 번에 받을 수 있는 길이를 넘었습니다. 새 채팅을 시작하세요."
    if status == 404 or "model not found" in low or ("not found" in low and "model" in low):
        return "선택한 모델을 서버에서 찾지 못했습니다. 다른 모델을 고르세요."
    if status in (401, 403):
        return "인증에 실패했습니다. API 키 또는 로그인을 확인하세요."
    if status in (400, 422):
        if "options" in low:
            return (
                "이 모델이 요청의 options 항목을 거부했습니다. "
                "API 키와 모델 등록은 유지됩니다. 다른 모델을 고르거나 다시 시도하세요."
            )
        return "모델이 이번 요청 형식을 거부했습니다. 다른 모델을 고르거나 다시 시도하세요."
    if status in (500, 502, 503, 504) or "overloaded" in low:
        return "모델 서버가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도하세요."
    if raw in ("모델 응답 실패", "(빈 응답)"):
        return "모델이 답을 만들지 못했습니다. 다시 시도하세요."
    return "요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요."


def is_cloud_auth_user_message(err: str) -> bool:
    return CLOUD_AUTH_ERROR_PREFIX in (err or "")


def cloud_model_blocked_without_login(model: str) -> bool:
    """클라우드 모델인데 Ollama 미로그인이면 True."""
    if not is_cloud_runtime_name(model):
        return False
    try:
        from iris.infrastructure.ollama_usage import ollama_cloud_signed_in

        return not ollama_cloud_signed_in()
    except Exception:
        return True


def resolve_initial_model(preferred: str, available: list[str]) -> str:
    """부팅·목록 로드 시 쓸 모델.

    클라우드인데 미로그인이면 로컬 설치 채팅 모델로 바꾼다.
    API runtime·로그인된 클라우드·로컬은 preferred 유지(목록에 있을 때).
    """
    from iris.storage.api_providers import is_api_runtime_model
    from iris.system.setup_protocol import prefer_chat_model

    names = [str(n).strip() for n in available if str(n).strip()]
    pref = (preferred or "").strip()
    if pref in ("(unset)",):
        pref = ""

    if pref and is_api_runtime_model(pref):
        return pref

    if pref and not cloud_model_blocked_without_login(pref):
        if not names or pref in names:
            return pref

    # 미로그인 클라우드 / 목록에 없는 preferred → 로컬
    local_hint = pref if pref and not is_cloud_runtime_name(pref) else ""
    local = prefer_chat_model(names, preferred=local_hint)
    if local:
        return local
    return pref


if __name__ == "__main__":
    assert looks_like_upstream_unauthorized("HTTP 401: Unauthorized")
    assert not looks_like_upstream_unauthorized("Invalid gateway API key")
    assert is_cloud_runtime_name("gemma4:31b-cloud")
    assert not is_cloud_runtime_name("exaone3.5:2.4b")
    assert CLOUD_AUTH_ERROR_PREFIX in format_hermes_sse_error(
        "HTTP 401: Unauthorized", model="gemma4:31b-cloud"
    )
    assert GATEWAY_AUTH_ERROR_PREFIX in format_hermes_http_401()
    assert "도구" in format_hermes_sse_error(
        "registry.ollama.ai/library/exaone3.5:2.4b does not support tools"
    )
    quota = (
        'Hermes: HTTP 429: [{"error":{"code":429,"message":'
        '"You exceeded your current quota, please check your plan and billing details. '
        'https://ai.google.dev/gemini-api/docs/rate-limits"}}]'
    )
    assert "Gemini API 사용 한도" in explain_chat_error(quota)
    assert "options" in explain_chat_error(
        "Hermes: HTTP 400 Unsupported parameter(s): options"
    )
    assert explain_chat_error(CLOUD_AUTH_USER_MSG) == CLOUD_AUTH_USER_MSG
    assert "연결하지 못했습니다" in explain_chat_error("Hermes 연결 실패: refused")
    assert "Iris Agent" in explain_chat_error("Hermes 연결 실패: refused")
    assert "hermes doctor" not in explain_chat_error(
        "custom rejected; run `hermes doctor` for details"
    ).lower()
    assert "Iris" in scrub_upstream_hermes_cli_hints("run hermes doctor now")
    assert "한도" in explain_chat_error("Ollama HTTP 429: rate limit")
    assert "답을 만들지 못했습니다" in explain_chat_error("모델 응답 실패")
    _timeout_ui = "응답 대기 시간이 초과됐습니다. 잠시 후 다시 시도하세요."
    assert explain_chat_error("엔진 응답을 읽지 못했습니다.") == _timeout_ui
    assert explain_chat_error(_timeout_ui) == _timeout_ui
    from iris.engine.types import EngineError, EngineErrorCode

    assert EngineError(EngineErrorCode.TURN_IDLE, "sidecar event timed out").user_message == _timeout_ui
    from unittest.mock import patch

    with patch(
        "iris.infrastructure.ollama_usage.ollama_cloud_signed_in", return_value=False
    ):
        assert (
            resolve_initial_model(
                "gemma4:31b-cloud", ["gemma4:31b-cloud", "exaone3.5:2.4b"]
            )
            == "exaone3.5:2.4b"
        )
        assert resolve_initial_model("", ["exaone3.5:2.4b"]) == "exaone3.5:2.4b"
    with patch(
        "iris.infrastructure.ollama_usage.ollama_cloud_signed_in", return_value=True
    ):
        assert (
            resolve_initial_model(
                "gemma4:31b-cloud", ["gemma4:31b-cloud", "exaone3.5:2.4b"]
            )
            == "gemma4:31b-cloud"
        )
    print("hermes_errors self-check ok")
