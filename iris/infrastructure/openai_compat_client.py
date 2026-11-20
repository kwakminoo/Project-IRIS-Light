"""OpenAI 호환 HTTP 클라이언트 — {base}/models · {base}/chat/completions.

Base URL과 인증 방식은 추정하지 않고 등록 시점에 HTTP로 실측하여 확정함
(`resolve_base_url`). `/v1`을 무조건 붙이는 문자열 규칙은 쓰지 않음.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris import __version__
from iris.runtime.stream_usage import parse_stream_usage

# 마지막 경로 조각이 이 중 하나면 사용자가 이미 버전 세그먼트까지 입력한 것으로 존중함
_VERSION_SEGMENTS = ("v1", "v1beta", "v1alpha", "v2", "openai", "api")
AUTH_STYLES = ("bearer", "x-api-key")
_SMOKE_LIMIT = 8  # 등록 테스트에서 대화 스모크를 시도할 최대 모델 수
IRIS_HTTP_USER_AGENT = f"Iris-Light/{__version__}"


def is_cloudflare_1010(detail: str) -> bool:
    text = (detail or "").casefold()
    return "error 1010" in text or "access denied (error: 1010)" in text


def _display_http_detail(status: int, detail: str) -> str:
    if status == 403 and is_cloudflare_1010(detail):
        return (
            "Cloudflare Error 1010: HTTP 클라이언트 식별자가 차단되었습니다. "
            "API 키 오류가 아닙니다. Iris User-Agent 또는 네트워크/IP 정책을 확인하세요."
        )
    return detail


class HttpFail(RuntimeError):
    """HTTP 실패. status 0은 연결 자체 실패(타임아웃·DNS 등)."""

    def __init__(self, status: int, detail: str) -> None:
        shown = _display_http_detail(status, detail)
        super().__init__(f"HTTP {status}: {shown}" if status else f"연결 실패: {shown}")
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class ProbeResult:
    """status: ok(목록+대화 성공) | partial(목록만) | error."""

    status: str
    base_url: str = ""
    auth_style: str = "bearer"
    models: list[str] = field(default_factory=list)
    detail: str = ""
    # Raw /models item dicts when listing succeeded. Empty on chat-only resolve.
    model_entries: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def normalize_base_url(base_url: str) -> str:
    """공백·후행 슬래시·`/chat/completions` 접미사만 제거함. `/v1`은 붙이지 않음."""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/chat/completions"):
        raw = raw[: -len("/chat/completions")]
    return raw.rstrip("/")


def base_url_candidates(raw: str) -> list[str]:
    """시도 순서대로 후보 반환. 첫 항목이 가장 유력함."""
    root = normalize_base_url(raw)
    if not root:
        return []
    last = root.rsplit("/", 1)[-1].lower()
    if last in _VERSION_SEGMENTS:
        return [root]
    return [f"{root}/v1", root]


def _auth_headers(api_key: str, auth_style: str = "bearer") -> dict[str, str]:
    h = {
        "User-Agent": IRIS_HTTP_USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    key = (api_key or "").strip()
    if not key:
        return h
    if auth_style == "x-api-key":
        h["x-api-key"] = key
        h["anthropic-version"] = "2023-06-01"
    else:
        h["Authorization"] = f"Bearer {key}"
    return h


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    auth_style: str = "bearer",
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = Request(
        url, data=data, headers=_auth_headers(api_key, auth_style), method=method
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise HttpFail(int(exc.code), detail or str(exc.reason)) from exc
    except URLError as exc:
        raise HttpFail(0, str(exc.reason)) from exc
    except (TimeoutError, OSError) as exc:
        raise HttpFail(0, str(exc)) from exc
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpFail(0, f"JSON 파싱 실패: {raw[:120]}") from exc


def _model_entries(data: Any) -> list[dict[str, Any]]:
    """Preserve raw /models item dicts. Drop rows without id. Dedupe by id."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        mid = str(it.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        row = dict(it)
        row["id"] = mid
        out.append(row)
    return out


def _model_ids(data: Any) -> list[str]:
    return [str(e["id"]) for e in _model_entries(data)]


def list_model_entries(
    base_url: str, api_key: str, *, auth_style: str = "bearer", timeout: float = 20.0
) -> list[dict[str, Any]]:
    """GET {base}/models and return raw item dicts (description/pricing/modality kept)."""
    root = normalize_base_url(base_url)
    if not root:
        raise ValueError("base_url이 비어 있습니다")
    data = _http_json(
        "GET", f"{root}/models", api_key=api_key, auth_style=auth_style, timeout=timeout
    )
    return _model_entries(data)


def list_models(
    base_url: str, api_key: str, *, auth_style: str = "bearer", timeout: float = 20.0
) -> list[str]:
    """Id-only wrapper for callers that do not need listing metadata."""
    return [str(e["id"]) for e in list_model_entries(
        base_url, api_key, auth_style=auth_style, timeout=timeout
    )]


def _try_candidates(
    candidates: list[str],
    api_key: str,
    attempt: Callable[[str, str], Any],
) -> tuple[str, str, Any, list[str]]:
    """후보 × 인증방식 순으로 attempt 시도. (후보, auth_style, 결과, 오류들).

    인증은 Bearer 우선이며 401/403일 때만 x-api-key로 1회 재시도함.
    """
    errors: list[str] = []
    has_key = bool((api_key or "").strip())
    for cand in candidates:
        for style in AUTH_STYLES:
            if style == "x-api-key" and not has_key:
                break
            try:
                return cand, style, attempt(cand, style), errors
            except HttpFail as exc:
                errors.append(f"{cand}: {exc}")
                if not (
                    style == "bearer"
                    and exc.status in (401, 403)
                    and not is_cloudflare_1010(exc.detail)
                ):
                    break
    return "", "", None, errors


def _resolve_base_url_full(
    raw: str,
    api_key: str,
    *,
    model: str = "",
    timeout: float = 6.0,
) -> tuple[str, str, list[str], str, list[dict[str, Any]]]:
    """(base_url, auth_style, models, detail, model_entries). 실패 시 base_url == ""."""
    candidates = base_url_candidates(raw)
    if not candidates:
        return "", "", [], "Base URL이 비어 있습니다", []

    cand, style, data, errors = _try_candidates(
        candidates,
        api_key,
        lambda c, s: _http_json(
            "GET", f"{c}/models", api_key=api_key, auth_style=s, timeout=timeout
        ),
    )
    if cand:
        entries = _model_entries(data)
        return (
            cand,
            style,
            [str(e["id"]) for e in entries],
            f"{cand}/models ok ({style})",
            entries,
        )

    # /models가 없는 게이트웨이 — 사용자가 모델을 직접 준 경우에만 chat으로 확정
    hint = (model or "").strip()
    if hint:
        cand, style, _, chat_errors = _try_candidates(
            candidates,
            api_key,
            lambda c, s: chat_smoke(c, api_key, hint, auth_style=s, timeout=timeout),
        )
        errors.extend(chat_errors)
        if cand:
            return cand, style, [hint], f"{cand}/chat/completions ok ({style})", []

    return "", "", [], " · ".join(errors[-3:]) or "Base URL 확정 실패", []


def resolve_base_url(
    raw: str,
    api_key: str,
    *,
    model: str = "",
    timeout: float = 6.0,
) -> tuple[str, str, list[str], str]:
    """(확정 base_url, auth_style, models, detail). 실패 시 base_url == ""."""
    base, style, models, detail, _entries = _resolve_base_url_full(
        raw, api_key, model=model, timeout=timeout
    )
    return base, style, models, detail


def probe(
    base_url: str,
    api_key: str,
    *,
    model: str = "",
    timeout: float = 25.0,
) -> ProbeResult:
    """연결 테스트 — Base URL·인증 방식을 확정하고 chat까지 실측함."""
    root, style, models, detail, entries = _resolve_base_url_full(
        base_url, api_key, model=model, timeout=min(timeout, 10.0)
    )
    if not root:
        return ProbeResult("error", detail=detail)
    # ponytail: 지정 모델 → 목록 앞쪽 순으로 최대 _SMOKE_LIMIT개만 스모크함. 첫 모델이
    # 은퇴·비채팅(Gemini 2.5 계열·TTS 실측)이어도 제공자를 실패로 몰지 않기 위함.
    # 천장: 모델별 정확한 상태는 선택 시 프로브(model_states)로 판정함.
    hint = (model or "").strip()
    tried: list[str] = [hint] if hint else []
    for m in models:
        if len(tried) >= _SMOKE_LIMIT:
            break
        if m not in tried:
            tried.append(m)
    listing = list(entries)
    if not tried:
        return ProbeResult(
            "partial",
            root,
            style,
            models,
            f"{detail} · 모델 0개 — 모델 id를 직접 입력하세요",
            model_entries=listing,
        )
    errors: list[str] = []
    for cand in tried:
        try:
            chat_smoke(root, api_key, cand, auth_style=style, timeout=timeout)
        except HttpFail as exc:
            errors.append(f"{cand}: {exc}")
            continue
        found = models or [cand]
        return ProbeResult(
            "ok",
            root,
            style,
            found,
            f"ok · {len(found)} models · 대화 검증 {cand} ({style})",
            model_entries=listing,
        )
    return ProbeResult(
        "partial",
        root,
        style,
        models,
        "목록은 되나 대화 실패 — " + " · ".join(errors[:2]),
        model_entries=listing,
    )


_PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "iris_probe",
        "description": "capability probe",
        "parameters": {"type": "object", "properties": {}},
    },
}


def chat_smoke(
    root: str,
    api_key: str,
    model: str,
    *,
    auth_style: str = "bearer",
    tools: bool = False,
    timeout: float = 20.0,
) -> None:
    """1토큰 chat 요청 1회. 실패 시 HttpFail. tools=True면 도구 1건을 실어 보냄."""
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    if tools:
        body["tools"] = [_PROBE_TOOL]
    _http_json(
        "POST",
        f"{root}/chat/completions",
        api_key=api_key,
        auth_style=auth_style,
        body=body,
        timeout=timeout,
    )


def stream_chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    auth_style: str = "bearer",
    timeout: float = 120.0,
    _include_usage: bool = True,
) -> Iterator[dict[str, Any]]:
    """Yield content, normalized token usage, and terminal state."""
    root = normalize_base_url(base_url)
    if not root:
        raise ValueError("base_url이 비어 있습니다")
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if _include_usage:
        body["stream_options"] = {"include_usage": True}
    from iris.runtime.attachment_context import trace_payload
    trace_payload("openai_compat", body)
    data = json.dumps(body).encode("utf-8")
    req = Request(
        f"{root}/chat/completions",
        data=data,
        headers=_auth_headers(api_key, auth_style),
        method="POST",
    )
    try:
        resp = urlopen(req, timeout=timeout)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        if (
            _include_usage
            and int(exc.code) == 400
            and "stream_options" in detail.lower()
        ):
            yield from stream_chat(
                base_url,
                api_key,
                model,
                messages,
                auth_style=auth_style,
                timeout=timeout,
                _include_usage=False,
            )
            return
        raise HttpFail(int(exc.code), detail or str(exc.reason)) from exc
    except URLError as exc:
        raise HttpFail(0, str(exc.reason)) from exc

    with resp:
        while True:
            line = resp.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if text.startswith(":"):
                continue
            if not text.startswith("data:"):
                continue
            payload = text[5:].strip()
            if payload == "[DONE]":
                yield {"content": None, "done": True}
                return
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = parse_stream_usage(obj)
            if usage is not None:
                yield {"content": None, "usage": usage, "done": False}
            choices = obj.get("choices") if isinstance(obj, dict) else None
            if not isinstance(choices, list) or not choices:
                continue
            ch0 = choices[0] if isinstance(choices[0], dict) else {}
            delta = ch0.get("delta") if isinstance(ch0, dict) else {}
            if not isinstance(delta, dict):
                delta = {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield {"content": content, "done": False}
            finish = ch0.get("finish_reason") if isinstance(ch0, dict) else None
            if finish:
                continue
    yield {"content": None, "done": True}


if __name__ == "__main__":
    assert normalize_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"
    assert normalize_base_url("https://x.com/v1/chat/completions") == "https://x.com/v1"
    assert base_url_candidates("https://api.openai.com") == [
        "https://api.openai.com/v1",
        "https://api.openai.com",
    ]
    assert base_url_candidates("https://generativelanguage.googleapis.com/v1beta/openai") == [
        "https://generativelanguage.googleapis.com/v1beta/openai"
    ]
    assert base_url_candidates("") == []
    assert "x-api-key" in _auth_headers("k", "x-api-key")
    assert _auth_headers("k")["Authorization"] == "Bearer k"
    assert _auth_headers("")["User-Agent"] == IRIS_HTTP_USER_AGENT
    assert is_cloudflare_1010("Cloudflare Error 1010")
    sample = {
        "data": [
            {
                "id": "org/free-chat",
                "description": "Official free blurb",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"modality": "text->text"},
            },
            {"name": "no-id"},
            {"id": "org/free-chat", "description": "dup drop"},
        ]
    }
    entries = _model_entries(sample)
    assert len(entries) == 1
    assert entries[0]["id"] == "org/free-chat"
    assert entries[0]["description"] == "Official free blurb"
    assert entries[0]["pricing"] == {"prompt": "0", "completion": "0"}
    assert _model_ids(sample) == ["org/free-chat"]
    print("openai_compat_client self-check ok")
