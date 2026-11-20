"""Incremental str chunks → part open/delta/close events.

Reuses iris.core.chat_block_parser.parse_chat_segments for fence/tool boundaries.
Incomplete fence locks into a code part and closes as code on finish (or when
following prose begins). content_chunk str-only is an adapter input, not the
sole canonical stream — PartStreamEvent is the parts-path contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from iris.core.chat_block_parser import (
    ChatSegment,
    CodeSegment,
    ProseSegment,
    ToolSegment,
    parse_chat_segments,
)
from iris.core.message_parts import CodePart, MessagePart, TextPart, ToolPart

PartKind = Literal["text", "code", "tool"]


@dataclass(frozen=True)
class PartOpen:
    part_id: str
    type: str  # text|code|tool|...
    language: str = ""
    name: str = ""


@dataclass(frozen=True)
class PartDelta:
    part_id: str
    text: str


@dataclass(frozen=True)
class PartClose:
    part_id: str


PartStreamEvent = PartOpen | PartDelta | PartClose


@dataclass
class _OpenPart:
    index: int
    part_id: str
    kind: PartKind
    emitted: int = 0
    language: str = ""
    name: str = ""
    text: str = ""


@dataclass
class PartStreamBuffer:
    """Feed str chunks; emit part events; snapshot MessagePart list for persist."""

    _raw: str = ""
    _seq: int = 0
    _committed: list[MessagePart] = field(default_factory=list)
    _open: _OpenPart | None = None
    _seg_count: int = 0

    def reset(self) -> None:
        self._raw = ""
        self._seq = 0
        self._committed.clear()
        self._open = None
        self._seg_count = 0

    def push(self, chunk: str) -> list[PartStreamEvent]:
        if not chunk:
            return []
        self._raw += chunk
        segs = parse_chat_segments(self._raw, final=False)
        return self._sync(segs, finishing=False)

    def finish(self) -> list[PartStreamEvent]:
        segs = parse_chat_segments(self._raw, final=True)
        return self._sync(segs, finishing=True)

    def parts(self) -> list[MessagePart]:
        out = list(self._committed)
        if self._open is not None:
            out.append(self._message_part(self._open))
        return out

    def _next_id(self, kind: PartKind) -> str:
        self._seq += 1
        return f"{kind}-{self._seq}"

    def _sync(
        self, segs: list[ChatSegment], *, finishing: bool
    ) -> list[PartStreamEvent]:
        events: list[PartStreamEvent] = []
        n = len(segs)
        if n < self._seg_count and self._open is not None:
            # Rare reshape: close whatever was open before rebuilding.
            events.extend(self._force_close_open())
            self._seg_count = len(self._committed)

        for i, seg in enumerate(segs):
            kind, text, lang, name = _payload(seg)
            is_last = i == n - 1
            # Non-last segments are locked. Last segment stays open mid-stream
            # unless the parser already closed a fence/tool. finish() closes all.
            if not is_last:
                should_close = True
            elif finishing:
                should_close = True
            else:
                should_close = isinstance(seg, (CodeSegment, ToolSegment)) and _segment_complete(
                    seg
                )

            if i < len(self._committed):
                # Already finalized this slot; content should be stable.
                continue

            if self._open is not None and self._open.index == i:
                events.extend(
                    self._delta_open(
                        text, lang=lang, name=name, allow_shrink=should_close
                    )
                )
                if should_close:
                    events.extend(self._close_open())
                continue

            if self._open is not None:
                # New segment while previous still open → lock previous as-is.
                events.extend(self._close_open())

            if not text and not should_close and kind == "text":
                # Wait for first prose bytes before opening an empty text shell.
                continue
            if not text and kind == "text" and should_close:
                continue

            pid = self._next_id(kind)
            events.append(
                PartOpen(part_id=pid, type=kind, language=lang, name=name)
            )
            self._open = _OpenPart(
                index=i,
                part_id=pid,
                kind=kind,
                emitted=0,
                language=lang,
                name=name,
                text="",
            )
            if text:
                events.extend(
                    self._delta_open(
                        text, lang=lang, name=name, allow_shrink=should_close
                    )
                )
            if should_close:
                events.extend(self._close_open())

        self._seg_count = n
        return events

    def _delta_open(
        self,
        text: str,
        *,
        lang: str = "",
        name: str = "",
        allow_shrink: bool = False,
    ) -> list[PartStreamEvent]:
        assert self._open is not None
        op = self._open
        if lang:
            op.language = lang
        if name:
            op.name = name
        if text == op.text:
            return []
        if text.startswith(op.text):
            piece = text[len(op.text) :]
            op.text = text
            op.emitted = len(text)
            return [PartDelta(part_id=op.part_id, text=piece)] if piece else []
        # Transient fence trim (_safe_partial_code) can shrink the visible tail.
        # Hold until close/finish applies the parser's finalized body.
        if op.text.startswith(text):
            if allow_shrink:
                op.text = text
                op.emitted = len(text)
            return []
        piece = text
        op.text = text
        op.emitted = len(text)
        return [PartDelta(part_id=op.part_id, text=piece)] if piece else []

    def _close_open(self) -> list[PartStreamEvent]:
        assert self._open is not None
        op = self._open
        self._committed.append(self._message_part(op))
        pid = op.part_id
        self._open = None
        return [PartClose(part_id=pid)]

    def _force_close_open(self) -> list[PartStreamEvent]:
        if self._open is None:
            return []
        return self._close_open()

    def _message_part(self, op: _OpenPart) -> MessagePart:
        if op.kind == "text":
            return TextPart(markdown=op.text)
        if op.kind == "code":
            return CodePart(language=op.language or "", source=op.text)
        if op.kind == "tool":
            return ToolPart(name=op.name or "tool", detail=op.text)
        return TextPart(markdown=op.text)


def _payload(seg: ChatSegment) -> tuple[PartKind, str, str, str]:
    if isinstance(seg, ProseSegment):
        return ("text", seg.text, "", "")
    if isinstance(seg, CodeSegment):
        return ("code", seg.code, seg.language or "", "")
    if isinstance(seg, ToolSegment):
        block = seg.block
        detail = "\n".join(
            x
            for x in (
                f"command: {block.command}" if block.command else "",
                f"output: {block.output}" if block.output else "",
            )
            if x
        )
        return ("tool", detail, "", block.title or "tool")
    return ("text", "", "", "")


def _segment_complete(seg: ChatSegment) -> bool:
    if isinstance(seg, ProseSegment):
        return bool(seg.complete)
    if isinstance(seg, CodeSegment):
        return bool(seg.complete)
    if isinstance(seg, ToolSegment):
        return bool(seg.complete)
    return True
