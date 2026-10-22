"""위키 본문 → 채팅 인용 칩 계약."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

WIKI_QUOTE_MIME = "application/x-iris-wiki-quote"
_MAX_QUOTE_CHARS = 4000


@dataclass(frozen=True)
class WikiQuote:
    note_rel: str
    title: str
    quote: str
    source: str = "wiki"

    def normalized(self) -> WikiQuote | None:
        note_rel = (self.note_rel or "").strip()
        title = (self.title or "").strip() or note_rel.rsplit("/", 1)[-1]
        quote = (self.quote or "").strip()
        if not note_rel or not quote:
            return None
        if len(quote) > _MAX_QUOTE_CHARS:
            quote = quote[:_MAX_QUOTE_CHARS].rstrip() + "…"
        return WikiQuote(note_rel=note_rel, title=title, quote=quote, source=(self.source or "wiki"))


def wiki_quote_to_payload(quote: WikiQuote) -> dict[str, str]:
    item = quote.normalized()
    if item is None:
        return {}
    return asdict(item)


def wiki_quote_from_payload(data: object) -> WikiQuote | None:
    if not isinstance(data, dict):
        return None
    raw = WikiQuote(
        note_rel=str(data.get("note_rel", "")),
        title=str(data.get("title", "")),
        quote=str(data.get("quote", "")),
        source=str(data.get("source", "wiki") or "wiki"),
    )
    return raw.normalized()


def encode_wiki_quote_bytes(quote: WikiQuote) -> bytes:
    payload = wiki_quote_to_payload(quote)
    if not payload:
        return b""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def decode_wiki_quote_bytes(raw: bytes | str | None) -> WikiQuote | None:
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return wiki_quote_from_payload(data)


def format_quotes_for_model(quotes: list[WikiQuote], user_text: str) -> str:
    """칩 UI는 별도. 모델에는 구조화 블록 + 사용자 문장."""
    blocks: list[str] = []
    for raw in quotes:
        q = raw.normalized()
        if q is None:
            continue
        blocks.append(
            f"[위키 인용]\n제목: {q.title}\n경로: {q.note_rel}\n내용:\n{q.quote}"
        )
    body = (user_text or "").strip()
    if blocks and body:
        return "\n\n".join(blocks) + "\n\n" + body
    if blocks:
        return "\n\n".join(blocks)
    return body


def chip_preview(quote: WikiQuote, *, max_chars: int = 120) -> str:
    q = quote.normalized()
    if q is None:
        return ""
    text = q.quote.replace("\n", " ")
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text
