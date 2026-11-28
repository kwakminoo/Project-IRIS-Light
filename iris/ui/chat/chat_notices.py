"""Chat system notices for H1 transcript (update / error / note / STT).

Domain shape for present_notice — not chat answers, so no TTS registration.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ChatNoticeAction:
    href: str
    label: str


@dataclass(frozen=True)
class ChatNotice:
    kind: str  # update | iris_agent_update | ollama_login | error | note | app_note | stt_pending
    body: str
    actions: tuple[ChatNoticeAction, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)


def _action_md(action: ChatNoticeAction) -> str:
    lab = (action.label or "").strip()
    href = (action.href or "").strip()
    if not lab or not href:
        return ""
    # Labels may already be "[Update]" — avoid [[Update]](href).
    if lab.startswith("[") and lab.endswith("]"):
        return f"{lab}({href})"
    return f"[{lab}]({href})"


def notice_markdown(notice: ChatNotice) -> str:
    """Visible prose + markdown action links for Unit A iris-* dispatch."""
    body = html.escape((notice.body or "").strip())
    if notice.kind in ("note", "app_note") and body and not body.startswith("_"):
        body = f"_{body}_"
    if not notice.actions:
        return body
    links = " ".join(
        md for a in notice.actions if (md := _action_md(a))
    )
    if body and links:
        return f"{body} {links}"
    return body or links


def notice_role(kind: str) -> str:
    if kind == "stt_pending":
        return "user"
    return "assistant"


def strip_action_links(markdown: str, href_prefix: str) -> str:
    """Remove markdown links whose href starts with href_prefix."""
    import re

    prefix = (href_prefix or "").strip()
    if not prefix:
        return markdown or ""
    escaped = re.escape(prefix)
    return re.sub(
        rf"\s*\[[^\]]*\]\({escaped}[^)]*\)",
        "",
        markdown or "",
    ).strip()
