"""Product-turn part contract — templates + gated AppPart construction.

Allowed ways to produce WritingPart / AppPart / CodePart on product turns:

1. SpeakTools ``app.present_html`` → AppPart (host calls ``gated_app_part``).
2. Fenced templates in assistant markdown:
   - `` ```iris-writing `` — JSON ``{title, body}`` or titled body (title line, blank, body).
   - `` ```iris-app `` — JSON ``{title, html, display_mode?}`` or titled body + complete HTML.
   - `` ```iris-code `` — JSON ``{language, source, filename?}`` or first-line language + source.
3. Ordinary language fences (`` ```python `` etc.) stay CodePart via the stream parser —
   not invented here from free prose.
4. Free markdown / raw ``<html>`` floods alone must **not** become AppPart or WritingPart.

Host rule: never append AppPart from ungated HTML. Use ``gated_app_part`` /
``try_parse_part_template`` / ``parts_from_assistant_payload`` only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from iris.core.message_parts import (
    AppPart,
    CitationPart,
    CodePart,
    DiagramPart,
    DisplayMode,
    ExecutionPart,
    ImagePart,
    MessagePart,
    TextPart,
    ToolPart,
    WritingPart,
    parse_part,
)

_PART_TYPES = (
    TextPart,
    WritingPart,
    CodePart,
    ToolPart,
    ImagePart,
    ExecutionPart,
    AppPart,
    CitationPart,
    DiagramPart,
)

_ROOT_SIGNALS = ("<html", "<!doctype", "<body")
_FENCE_RE = re.compile(
    r"```(iris-writing|iris-app|iris-code)[ \t]*\r?\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_TEMPLATE_LANGS = frozenset({"iris-writing", "iris-app", "iris-code"})
_DISPLAY_MODES: frozenset[str] = frozenset({"inline", "pip", "fullscreen"})


class IncompleteAppHtmlError(ValueError):
    """HTML is empty or missing a root document signal."""


class PartContractError(ValueError):
    """Payload violated the product part contract."""


def require_complete_app_html(html_text: str) -> str:
    """Validate app HTML at the present/template boundary. Returns stripped text."""
    if not isinstance(html_text, str):
        raise IncompleteAppHtmlError("app html must be a string")
    text = html_text.strip()
    if not text:
        raise IncompleteAppHtmlError("app html is empty")
    lower = text.lower()
    if any(sig in lower for sig in _ROOT_SIGNALS):
        return text
    raise IncompleteAppHtmlError(
        "app html must be a complete document "
        "(contains <html, <!DOCTYPE, or <body>)"
    )


def gated_app_part(
    title: str,
    html: str,
    display_mode: str = "inline",
) -> AppPart:
    """Only approved constructor for AppPart from HTML (present + iris-app)."""
    gated = require_complete_app_html(html)
    mode = _normalize_display_mode(display_mode)
    label = (title or "").strip() or "앱"
    return AppPart(title=label, html=gated, display_mode=mode)


def assert_app_part_gated(part: AppPart) -> AppPart:
    """Raise if an AppPart slipped through without a complete document."""
    if not isinstance(part, AppPart):
        raise PartContractError(f"expected AppPart, got {type(part)!r}")
    require_complete_app_html(part.html)
    return part


def try_parse_part_template(markdown_or_fence: str) -> MessagePart | None:
    """Parse one iris-* fence (or its inner body with lang prefix). Else None.

    Free HTML / ordinary markdown returns None — never invents AppPart/WritingPart.
    Incomplete iris-app HTML raises IncompleteAppHtmlError.
    """
    if not isinstance(markdown_or_fence, str):
        return None
    raw = markdown_or_fence.strip()
    if not raw:
        return None
    lang, body = _split_template(raw)
    if lang is None or body is None:
        return None
    if lang == "iris-writing":
        return _parse_writing_body(body)
    if lang == "iris-app":
        return _parse_app_body(body)
    if lang == "iris-code":
        return _parse_code_body(body)
    return None


def parts_from_assistant_payload(
    *,
    text: str | None = None,
    parts: Sequence[Any] | None = None,
) -> list[MessagePart]:
    """Merge explicit parts, else text + iris-* template fences only.

    Explicit ``parts`` win (list of MessagePart or serde dicts). AppParts in that
    list are re-gated. Without parts, free prose stays TextPart; only
    ``iris-writing`` / ``iris-app`` / ``iris-code`` fences become typed parts.
    Raw ``<html>`` in prose is never promoted to AppPart.
    """
    if parts is not None:
        return _gated_explicit_parts(parts)

    src = text if isinstance(text, str) else ""
    if not src:
        return []

    out: list[MessagePart] = []
    cursor = 0
    for match in _FENCE_RE.finditer(src):
        before = src[cursor : match.start()]
        if before.strip():
            out.append(TextPart(markdown=before))
        elif before and out and isinstance(out[-1], TextPart):
            out[-1] = TextPart(markdown=out[-1].markdown + before)
        lang = match.group(1).lower()
        body = match.group(2)
        parsed = try_parse_part_template(f"```{lang}\n{body}```")
        if parsed is None:
            # Unknown/failed template — keep as text (should not happen for iris-*).
            out.append(TextPart(markdown=match.group(0)))
        else:
            out.append(parsed)
        cursor = match.end()
    tail = src[cursor:]
    if tail.strip() or (tail and not out):
        out.append(TextPart(markdown=tail if out else src))
    elif not out:
        out.append(TextPart(markdown=src))
    return out


def _gated_explicit_parts(parts: Sequence[Any]) -> list[MessagePart]:
    out: list[MessagePart] = []
    for item in parts:
        if isinstance(item, _PART_TYPES):
            part: MessagePart = item
        elif isinstance(item, Mapping):
            part = parse_part(item)
        else:
            raise PartContractError(f"invalid part item: {type(item)!r}")
        if isinstance(part, AppPart):
            out.append(
                gated_app_part(part.title, part.html, display_mode=part.display_mode)
            )
        else:
            out.append(part)
    return out


def _normalize_display_mode(mode: str | None) -> DisplayMode:
    raw = (mode or "inline").strip().lower()
    if raw in _DISPLAY_MODES:
        return raw  # type: ignore[return-value]
    return "inline"


def _split_template(raw: str) -> tuple[str | None, str | None]:
    m = _FENCE_RE.fullmatch(raw) or _FENCE_RE.search(raw)
    if m and m.group(0).strip() == raw:
        return m.group(1).lower(), m.group(2)
    # Bare "iris-writing\n..." without fences — not accepted; contract is fenced.
    first, _, rest = raw.partition("\n")
    head = first.strip().lower()
    if head in _TEMPLATE_LANGS and rest:
        # Allow lang-only prefix when caller passes fence-inner with info line.
        return head, rest
    return None, None


def _try_json_object(body: str) -> dict[str, Any] | None:
    text = body.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _titled_body(body: str) -> tuple[str, str]:
    lines = body.splitlines()
    if not lines:
        return "", ""
    title = lines[0].strip()
    if len(lines) == 1:
        return title, ""
    # Optional blank line after title.
    rest = lines[1:]
    if rest and not rest[0].strip():
        rest = rest[1:]
    return title, "\n".join(rest)


def _parse_writing_body(body: str) -> WritingPart:
    data = _try_json_object(body)
    if data is not None:
        title = str(data.get("title") or "").strip()
        body_text = data.get("body")
        if not isinstance(body_text, str):
            body_text = str(body_text or "")
        return WritingPart(title=title or "초안", body=body_text)
    title, rest = _titled_body(body)
    if not rest and title:
        # Single block without blank title line → whole body is the draft.
        return WritingPart(title="초안", body=body.strip())
    return WritingPart(title=title or "초안", body=rest)


def _parse_app_body(body: str) -> AppPart:
    data = _try_json_object(body)
    if data is not None:
        title = str(data.get("title") or "").strip() or "앱"
        html = data.get("html")
        html_text = html if isinstance(html, str) else ""
        mode = data.get("display_mode", data.get("displayMode", "inline"))
        return gated_app_part(title, html_text, display_mode=str(mode or "inline"))
    title, rest = _titled_body(body)
    html_text = rest if rest.strip() else body.strip()
    if rest.strip():
        return gated_app_part(title or "앱", html_text)
    # Whole body is HTML (no title line).
    return gated_app_part("앱", body)


def _parse_code_body(body: str) -> CodePart:
    data = _try_json_object(body)
    if data is not None:
        language = str(data.get("language") or "").strip() or "text"
        source = data.get("source")
        if not isinstance(source, str):
            source = str(source or "")
        filename = str(data.get("filename") or "")
        return CodePart(language=language, source=source, filename=filename)
    title, rest = _titled_body(body)
    if rest:
        return CodePart(language=title or "text", source=rest)
    return CodePart(language="text", source=body.strip())
