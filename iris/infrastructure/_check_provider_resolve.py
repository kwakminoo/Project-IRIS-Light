"""Base URL·인증 실측 해석 self-check — urlopen을 가짜 응답 테이블로 대체함.

네트워크 없이 순수 로직만 검증함. 실제 키 스모크는 별건임.
"""

from __future__ import annotations

import io
import json
from contextlib import contextmanager
from urllib.error import HTTPError

from iris.infrastructure import openai_compat_client as oai


class _Resp:
    def __init__(self, payload: str) -> None:
        self._raw = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


@contextmanager
def fake_http(handler, log: list[tuple[str, str]] | None = None):
    """handler(url, auth_style, body) -> (code, payload). urlopen만 대체함."""
    original = oai.urlopen

    def fake(req, timeout=None):  # noqa: ANN001, ARG001
        style = "x-api-key" if req.get_header("X-api-key") else "bearer"
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        if log is not None:
            log.append((req.full_url, style))
        code, payload = handler(req.full_url, style, body)
        if code != 200:
            raise HTTPError(
                req.full_url, code, payload, {}, io.BytesIO(payload.encode("utf-8"))
            )
        return _Resp(payload)

    oai.urlopen = fake
    try:
        yield
    finally:
        oai.urlopen = original


def _models_payload(*ids: str) -> str:
    return json.dumps({"data": [{"id": i} for i in ids]})


def _only(ok_url: str, payload: str):
    """ok_url만 200, 나머지는 404."""

    def handler(url: str, _style: str, _body):  # noqa: ANN001
        if url == ok_url:
            return 200, payload
        return 404, '{"error":"not found"}'

    return handler


def check_candidates() -> None:
    assert oai.base_url_candidates("https://api.openai.com") == [
        "https://api.openai.com/v1",
        "https://api.openai.com",
    ]
    # 연번 5 — 이미 버전 세그먼트까지 입력한 URL에 /v1을 덧붙이지 않음
    assert oai.base_url_candidates(
        "https://generativelanguage.googleapis.com/v1beta/openai"
    ) == ["https://generativelanguage.googleapis.com/v1beta/openai"]
    assert oai.base_url_candidates("https://x.com/v1/chat/completions") == [
        "https://x.com/v1"
    ]
    assert oai.base_url_candidates("http://127.0.0.1:1234/v1") == [
        "http://127.0.0.1:1234/v1"
    ]
    assert oai.base_url_candidates("  ") == []


def check_resolve_root_and_verbatim() -> None:
    with fake_http(_only("https://api.openai.com/v1/models", _models_payload("gpt-4o"))):
        base, style, models, _ = oai.resolve_base_url("https://api.openai.com", "sk-x")
    assert base == "https://api.openai.com/v1", base
    assert style == "bearer" and models == ["gpt-4o"]

    gemini = "https://generativelanguage.googleapis.com/v1beta/openai"
    with fake_http(_only(f"{gemini}/models", _models_payload("gemini-2.0-flash"))):
        base, _, models, _ = oai.resolve_base_url(gemini, "key")
    assert base == gemini, base
    assert models == ["gemini-2.0-flash"]


def check_auth_fallback() -> None:
    def handler(url: str, style: str, _body):  # noqa: ANN001
        if url != "https://api.anthropic.com/v1/models":
            return 404, "{}"
        if style == "bearer":
            return 401, '{"error":"authentication_error"}'
        return 200, _models_payload("claude-sonnet-4")

    log: list[tuple[str, str]] = []
    with fake_http(handler, log):
        base, style, models, _ = oai.resolve_base_url(
            "https://api.anthropic.com/v1", "sk-ant"
        )
    assert style == "x-api-key", style
    assert base == "https://api.anthropic.com/v1" and models == ["claude-sonnet-4"]
    # 재시도는 1회만 — bearer → x-api-key
    assert [s for _, s in log] == ["bearer", "x-api-key"], log

    # 키가 없으면 x-api-key 재시도를 하지 않음 (로컬 서버 경로)
    log.clear()
    with fake_http(lambda *_a: (401, "{}"), log):
        base, _, _, detail = oai.resolve_base_url("http://127.0.0.1:8000/v1", "")
    assert base == "" and detail
    assert [s for _, s in log] == ["bearer"], log


def check_resolve_failure_has_no_fallback() -> None:
    """회귀 가드 — 확정 실패 시 하드코딩 목록이 아니라 빈 목록 + 사유."""
    with fake_http(lambda *_a: (404, '{"error":"no such endpoint"}')):
        base, style, models, detail = oai.resolve_base_url("https://nope.example", "k")
    assert base == "" and style == "" and models == []
    assert "404" in detail, detail


def check_resolve_via_chat_when_no_models_endpoint() -> None:
    def handler(url: str, _style: str, _body):  # noqa: ANN001
        if url == "https://gw.example/v1/chat/completions":
            return 200, '{"choices":[{"message":{"content":"pong"}}]}'
        return 404, "{}"

    with fake_http(handler):
        base, _, models, detail = oai.resolve_base_url(
            "https://gw.example", "k", model="my-model"
        )
    assert base == "https://gw.example/v1", base
    assert models == ["my-model"] and "chat/completions ok" in detail


def check_probe_states() -> None:
    root = "http://127.0.0.1:1234/v1"

    def ok_handler(url: str, _style: str, _body):  # noqa: ANN001
        if url == f"{root}/models":
            return 200, _models_payload("local-model")
        if url == f"{root}/chat/completions":
            return 200, '{"choices":[{"message":{"content":"pong"}}]}'
        return 404, "{}"

    with fake_http(ok_handler):
        result = oai.probe(root, "")
    assert result.status == "ok" and result.ok, result
    assert result.base_url == root and result.models == ["local-model"]

    # 첫 모델이 은퇴(404)여도 다음 모델이 되면 ok — Gemini 2.5 계열 실측 사례
    def retired_first(url: str, _style: str, body):  # noqa: ANN001
        if url == f"{root}/models":
            return 200, _models_payload("retired-model", "live-model")
        if body and body.get("model") == "retired-model":
            return 404, '{"error":"no longer available to new users"}'
        return 200, '{"choices":[{"message":{"content":"pong"}}]}'

    with fake_http(retired_first):
        result = oai.probe(root, "")
    assert result.status == "ok", result
    assert "live-model" in result.detail and result.models == ["retired-model", "live-model"]

    def partial_handler(url: str, _style: str, _body):  # noqa: ANN001
        if url == f"{root}/models":
            return 200, _models_payload("local-model")
        return 400, '{"error":"model not loaded"}'

    with fake_http(partial_handler):
        result = oai.probe(root, "")
    # 연번: 프로브 실패를 ok로 보고하는 경로 금지
    assert result.status == "partial" and not result.ok, result
    assert "대화 실패" in result.detail, result.detail

    with fake_http(lambda *_a: (404, "{}")):
        result = oai.probe(root, "")
    assert result.status == "error" and result.base_url == "", result

    def empty_models(url: str, _style: str, _body):  # noqa: ANN001
        return (200, json.dumps({"data": []})) if url.endswith("/models") else (404, "{}")

    with fake_http(empty_models):
        result = oai.probe(root, "")
    assert result.status == "partial" and result.models == [], result


def check_tool_support_probe() -> None:
    """도구지원 3-상태 — 200→yes / 400(tool 언급)→no / 429→unknown / 404→unavailable."""
    from iris.infrastructure.api_model_meta import verify_model

    root = "https://p.example/v1"
    ok_reply = '{"choices":[{"message":{"content":"pong"}}]}'

    with fake_http(lambda *_a: (200, ok_reply)):
        assert verify_model(root, "k", "m")[:2] == ("ok", "yes")

    def tools_rejected(_url: str, _style: str, body):  # noqa: ANN001
        if body and body.get("tools"):
            return 400, '{"error":"Function calling is not supported for this model"}'
        return 200, ok_reply

    assert verify_model_with(tools_rejected, root)[:2] == ("ok", "no")

    # 도구도 대화도 거부 — 모델 자체가 없음
    assert verify_model_with(lambda *_a: (404, '{"error":"no longer available"}'), root)[:2] == (
        "unavailable",
        "unknown",
    )
    # 쿼터·일시 장애는 모델 탓이 아니므로 미확정으로 남김
    assert verify_model_with(lambda *_a: (429, '{"error":"rate limit"}'), root)[:2] == (
        "unverified",
        "unknown",
    )
    assert verify_model_with(lambda *_a: (503, '{"error":"overloaded"}'), root)[:2] == (
        "unverified",
        "unknown",
    )
    # tools 언급 없는 400 — 비채팅 모달리티 → 목록에서 제외
    assert verify_model_with(lambda *_a: (400, '{"error":"input must be text embedding"}'), root)[
        :2
    ] == ("unavailable", "unknown")


def verify_model_with(handler, root: str):
    from iris.infrastructure.api_model_meta import verify_model

    with fake_http(handler):
        return verify_model(root, "k", "m")


def main() -> int:
    check_candidates()
    check_resolve_root_and_verbatim()
    check_auth_fallback()
    check_resolve_failure_has_no_fallback()
    check_resolve_via_chat_when_no_models_endpoint()
    check_probe_states()
    check_tool_support_probe()
    print("provider_resolve self-check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
