"""스캔 PDF·설명용 이미지를 채팅 모델 비전으로 글자 옮기기."""

from __future__ import annotations

import base64

_PROMPT = (
    "다음은 자료 페이지 이미지다. 보이는 글자를 페이지 순서대로 옮겨 적어라. "
    "글자가 없으면 그림이 무엇을 보여 주는지 짧게 적어라. "
    "보이지 않는 내용은 만들지 마라. 설명 제목은 붙이지 마라."
)


def _ask(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        return _PROMPT
    return (
        text
        + "\n\n보이는 글자만 적어라. 글자가 없으면 그림이 무엇인지 짧게 적어라. "
        "보이지 않는 내용은 만들지 마라."
    )


def transcribe_images(
    pngs: list[bytes],
    *,
    model: str,
    ollama_base_url: str,
    api_base_url: str = "",
    api_key: str = "",
    auth_style: str = "bearer",
    prompt: str = "",
) -> str:
    """PNG 바이트를 한 번 보내고 옮긴 글자만 받는다. 실패하면 빈 문자열."""
    images = [png for png in pngs if png]
    name = (model or "").strip()
    if not images or not name:
        return ""
    ask = _ask(prompt)
    if not (api_base_url or "").strip():
        from iris.infrastructure.ollama_client import OllamaClient

        try:
            return OllamaClient(ollama_base_url).chat_once_with_images(
                name, ask, images, timeout_sec=60.0
            )
        except Exception:
            return ""
    from iris.infrastructure.openai_compat_client import _http_json, normalize_base_url

    root = normalize_base_url(api_base_url)
    if not root:
        return ""
    content: list[dict[str, object]] = [{"type": "text", "text": ask}]
    for png in images:
        data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    try:
        obj = _http_json(
            "POST",
            f"{root}/chat/completions",
            api_key=api_key,
            auth_style=auth_style,
            body={"model": name, "stream": False, "messages": [{"role": "user", "content": content}]},
            timeout=60.0,
        )
    except Exception:
        return ""
    choices = obj.get("choices") if isinstance(obj, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    got = message.get("content") if isinstance(message, dict) else ""
    if isinstance(got, list):
        parts = [
            str(part.get("text") or "")
            for part in got
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(parts)
    return str(got or "")
