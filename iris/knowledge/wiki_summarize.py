"""위키 저장용 본문 요약 (Ollama 단발)."""

from __future__ import annotations

_SYSTEM = (
    "You summarize source text for an Iris Wiki note. "
    "Output Korean markdown: short title line optional, then bullet facts, "
    "key quotes if any, and a short conclusion. No preamble."
)


def summarize_for_wiki(
    text: str,
    *,
    model: str,
    ollama_base_url: str,
    max_input_chars: int = 24_000,
) -> str:
    body = (text or "").strip()
    if not body:
        raise ValueError("empty text")
    if len(body) > max_input_chars:
        body = body[:max_input_chars] + "\n\n… (input truncated for summary)"
    from iris.infrastructure.ollama_client import OllamaClient

    client = OllamaClient(base_url=ollama_base_url)
    prompt = f"다음 자료를 Iris Wiki 노트용으로 요약해 주세요.\n\n---\n{body}\n---"
    out = client.chat_once_with_images(
        model,
        prompt,
        [],
        system=_SYSTEM,
        timeout_sec=120.0,
    )
    summary = (out or "").strip()
    if not summary:
        raise RuntimeError("empty summary from model")
    return summary
