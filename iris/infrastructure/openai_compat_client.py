"""OpenAI 호환 HTTP 클라이언트 — /v1/models · /v1/chat/completions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def normalize_base_url(base_url: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return ""
    # 사용자가 .../v1 또는 루트만 넣어도 /v1 기준으로 맞춤
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def _auth_headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    key = (api_key or "").strip()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=_auth_headers(api_key), method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"연결 실패: {exc.reason}") from exc
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 파싱 실패: {raw[:120]}") from exc


def list_models(base_url: str, api_key: str, *, timeout: float = 20.0) -> list[str]:
    root = normalize_base_url(base_url)
    if not root:
        raise ValueError("base_url이 비어 있습니다")
    data = _http_json("GET", f"{root}/models", api_key=api_key, timeout=timeout)
    names: list[str] = []
    items = data.get("data") if isinstance(data, dict) else None
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                mid = str(it.get("id") or "").strip()
                if mid and mid not in names:
                    names.append(mid)
    return names


def probe(
    base_url: str,
    api_key: str,
    *,
    model: str = "",
    timeout: float = 25.0,
) -> tuple[bool, str, list[str]]:
    """연결 테스트. (ok, detail, models)."""
    root = normalize_base_url(base_url)
    if not root:
        return False, "Base URL이 비어 있습니다", []
    models: list[str] = []
    try:
        models = list_models(base_url, api_key, timeout=min(timeout, 20.0))
    except Exception as exc:
        # /models 실패해도 chat으로 재시도 가능
        models_err = str(exc)[:200]
        if not (model or "").strip():
            return False, f"/models 실패: {models_err}", []
        # 수동 모델로 chat 스모크
        try:
            _chat_smoke(root, api_key, model.strip(), timeout=timeout)
            return True, f"chat ok (models 목록 실패: {models_err})", [model.strip()]
        except Exception as chat_exc:
            return False, f"/models: {models_err} · chat: {chat_exc}", []

    use_model = (model or "").strip() or (models[0] if models else "")
    if not use_model:
        return True, "models ok (모델 0개 — 수동 목록을 입력하세요)", models
    try:
        _chat_smoke(root, api_key, use_model, timeout=timeout)
    except Exception as exc:
        # 목록은 됐으니 연결은 부분 성공으로 볼 수 있음 — 키/권한은 통과
        return True, f"models ok · chat 스모크 스킵/실패: {exc}", models
    return True, f"ok · {len(models)} models", models


def _chat_smoke(root: str, api_key: str, model: str, *, timeout: float) -> None:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    _http_json(
        "POST",
        f"{root}/chat/completions",
        api_key=api_key,
        body=body,
        timeout=timeout,
    )


def stream_chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    timeout: float = 120.0,
) -> Iterator[dict[str, Any]]:
    """yield {"content": str|None, "done": bool}."""
    root = normalize_base_url(base_url)
    if not root:
        raise ValueError("base_url이 비어 있습니다")
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    data = json.dumps(body).encode("utf-8")
    req = Request(
        f"{root}/chat/completions",
        data=data,
        headers=_auth_headers(api_key),
        method="POST",
    )
    try:
        resp = urlopen(req, timeout=timeout)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"연결 실패: {exc.reason}") from exc

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
                yield {"content": None, "done": True}
                return
    yield {"content": None, "done": True}


if __name__ == "__main__":
    assert normalize_base_url("https://api.openai.com") == "https://api.openai.com/v1"
    assert normalize_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"
    print("openai_compat_client self-check ok")
