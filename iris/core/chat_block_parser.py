"""스트리밍 채팅 본문 — prose / fenced_code / tool 블록 점진 파싱."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from iris.ui.chat.chat_blocks import FencedCodeBlock, ToolShellBlock, tool_block_markers

_TOOL_START = re.compile(r"IRIS_TOOL_([A-Za-z0-9_-]+)_START")
_FENCE = "```"


class RenderOpKind(Enum):
    REPLACE_PROSE = "replace_prose"
    INSERT_CODE = "insert_code"
    INSERT_TOOL = "insert_tool"


@dataclass(frozen=True)
class RenderOp:
    kind: RenderOpKind
    prose: str = ""
    code: FencedCodeBlock | None = None
    tool: ToolShellBlock | None = None


@dataclass
class ProseSegment:
    text: str
    complete: bool = True


@dataclass
class CodeSegment:
    language: str
    code: str
    complete: bool = False


@dataclass
class ToolSegment:
    block: ToolShellBlock
    complete: bool = False


ChatSegment = ProseSegment | CodeSegment | ToolSegment


def prose_char_count(text: str) -> int:
    """TTS·타이핑 동기화용 — code/tool 구간은 제외한 prose 글자 수."""
    return sum(len(seg.text) for seg in parse_chat_segments(text) if isinstance(seg, ProseSegment))


def parse_chat_segments(text: str) -> list[ChatSegment]:
    """전체 버퍼를 prose / code / tool 세그먼트로 분해."""
    raw = text or ""
    if not raw:
        return []

    segments: list[ChatSegment] = []
    i = 0
    n = len(raw)

    while i < n:
        tool_m = _TOOL_START.match(raw, i)
        if tool_m:
            block_id = tool_m.group(1)
            start_marker, end_marker = tool_block_markers(block_id)
            end_idx = raw.find(end_marker, tool_m.end())
            if end_idx < 0:
                body = raw[tool_m.end() :]
                segments.append(
                    ToolSegment(
                        block=_parse_tool_body(block_id, body),
                        complete=False,
                    )
                )
                return segments
            body = raw[tool_m.end() : end_idx]
            segments.append(
                ToolSegment(
                    block=_parse_tool_body(block_id, body),
                    complete=True,
                )
            )
            i = end_idx + len(end_marker)
            continue

        if raw.startswith(_FENCE, i):
            fence_end = i + 3
            nl = raw.find("\n", fence_end)
            if nl < 0:
                # lang 줄이 아직 안 끝남 — prose로 보류하지 않고 code 대기
                lang = raw[fence_end:].strip()
                segments.append(CodeSegment(language=lang, code="", complete=False))
                return segments
            lang = raw[fence_end:nl].strip()
            code_start = nl + 1
            tail = raw[code_start:]
            close_idx = _find_closing_fence(tail)
            if close_idx < 0:
                safe_code = _safe_partial_code(tail)
                segments.append(
                    CodeSegment(language=lang, code=safe_code, complete=False)
                )
                return segments
            code = tail[:close_idx]
            segments.append(
                CodeSegment(
                    language=lang,
                    code=code.rstrip("\n"),
                    complete=True,
                )
            )
            i = code_start + close_idx + 3
            continue

        next_special = _next_special_index(raw, i)
        if next_special < 0:
            segments.append(ProseSegment(text=raw[i:], complete=True))
            break
        if next_special > i:
            segments.append(ProseSegment(text=raw[i:next_special], complete=True))
        i = next_special

    return segments


def visible_prose_from_segments(
    segments: list[ChatSegment],
    typing_index: int,
    *,
    render_markdown: bool = False,
) -> str:
    """타이핑 인덱스까지 보일 prose만 이어 붙인다 (code/tool 제외)."""
    from iris.ui.chat.chat_display import visible_typing_text

    remaining = max(0, int(typing_index))
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, ProseSegment):
            if remaining <= 0:
                break
            take = seg.text[:remaining]
            remaining -= len(take)
            if take:
                parts.append(
                    visible_typing_text(take, len(take), render_markdown=render_markdown)
                    if render_markdown
                    else take
                )
        elif isinstance(seg, (CodeSegment, ToolSegment)):
            continue
        else:
            continue
    return "".join(parts)


def streaming_body_segments(
    segments: list[ChatSegment],
    typing_index: int,
    *,
    render_markdown: bool = False,
) -> list[ChatSegment]:
    """렌더용 — code/tool은 즉시, prose는 typing_index까지."""
    remaining = max(0, int(typing_index))
    out: list[ChatSegment] = []
    for seg in segments:
        if isinstance(seg, ProseSegment):
            if remaining <= 0:
                if not seg.complete:
                    out.append(ProseSegment(text="", complete=False))
                break
            take = seg.text[:remaining]
            remaining -= len(take)
            out.append(
                ProseSegment(
                    text=take,
                    complete=seg.complete and remaining <= 0 and len(take) == len(seg.text),
                )
            )
            if len(take) < len(seg.text):
                break
        else:
            out.append(seg)
    return out


@dataclass
class ChatBlockBuffer:
    """청크 단위 feed — 마지막 prose tail 변경·code/tool 확정 시 RenderOp emit."""

    _raw: str = ""
    _last_prose_tail: str = ""
    _emitted_codes: int = 0
    _emitted_tools: int = 0
    _segments: list[ChatSegment] = field(default_factory=list)

    def reset(self) -> None:
        self._raw = ""
        self._last_prose_tail = ""
        self._emitted_codes = 0
        self._emitted_tools = 0
        self._segments = []

    def feed(self, chunk: str) -> list[RenderOp]:
        if not chunk:
            return []
        self._raw += chunk
        self._segments = parse_chat_segments(self._raw)
        return self._diff_ops()

    def set_final(self, text: str) -> list[RenderOp]:
        """스트림 종료 — 정규화 본문으로 확정."""
        self._raw = text or ""
        self._segments = parse_chat_segments(self._raw)
        return self._diff_ops()

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def segments(self) -> list[ChatSegment]:
        return list(self._segments)

    def _diff_ops(self) -> list[RenderOp]:
        ops: list[RenderOp] = []
        prose_tail = _prose_tail(self._segments)
        if prose_tail != self._last_prose_tail:
            self._last_prose_tail = prose_tail
            ops.append(RenderOp(kind=RenderOpKind.REPLACE_PROSE, prose=prose_tail))

        code_count = sum(1 for s in self._segments if isinstance(s, CodeSegment))
        while self._emitted_codes < code_count:
            seg = _nth_code(self._segments, self._emitted_codes)
            if seg is None:
                break
            self._emitted_codes += 1
            ops.append(
                RenderOp(
                    kind=RenderOpKind.INSERT_CODE,
                    code=FencedCodeBlock(seg.code, language=seg.language),
                )
            )

        tool_count = sum(
            1
            for s in self._segments
            if isinstance(s, ToolSegment) and s.complete
        )
        while self._emitted_tools < tool_count:
            seg = _nth_complete_tool(self._segments, self._emitted_tools)
            if seg is None:
                break
            self._emitted_tools += 1
            ops.append(
                RenderOp(kind=RenderOpKind.INSERT_TOOL, tool=seg.block)
            )

        return ops


def _next_special_index(raw: str, start: int) -> int:
    tool_idx = raw.find("IRIS_TOOL_", start)
    fence_idx = raw.find(_FENCE, start)
    candidates = [i for i in (tool_idx, fence_idx) if i >= 0]
    return min(candidates) if candidates else -1


def _find_closing_fence(tail: str) -> int:
    """닫는 ``` 위치 — 청크 경계에서 ``` 가 쪼개질 수 있어 끝 2글자는 보류."""
    idx = tail.find(_FENCE)
    if idx < 0:
        return -1
    if idx + 3 > len(tail):
        return -1
    # ponytail: tail 끝이 ` 또는 `` 이면 닫는 펜스일 수 있어 미확정
    if tail.endswith("`") and not tail.endswith(_FENCE):
        if tail.count("`", idx) < 3:
            return -1
    if len(tail) - idx == 2 and tail[-2:] == "``":
        return -1
    return idx


def _safe_partial_code(tail: str) -> str:
    """스트리밍 중 — 닫는 ``` 후보 2글자 보류."""
    if len(tail) >= 2 and tail[-2:] in ("``", "`" + tail[-1:]):
        if tail.endswith("``"):
            return tail[:-2]
        if tail.endswith("`") and not tail.endswith(_FENCE):
            return tail[:-1]
    return tail


def _prose_tail(segments: list[ChatSegment]) -> str:
    for seg in reversed(segments):
        if isinstance(seg, ProseSegment):
            return seg.text
    return ""


def _nth_code(segments: list[ChatSegment], n: int) -> CodeSegment | None:
    seen = 0
    for seg in segments:
        if isinstance(seg, CodeSegment):
            if seen == n:
                return seg
            seen += 1
    return None


def _nth_complete_tool(segments: list[ChatSegment], n: int) -> ToolSegment | None:
    seen = 0
    for seg in segments:
        if isinstance(seg, ToolSegment) and seg.complete:
            if seen == n:
                return seg
            seen += 1
    return None


def _parse_tool_body(block_id: str, body: str) -> ToolShellBlock:
    title = "Shell"
    command = ""
    output = ""
    status = "ok"
    parsed_any = False
    for line in (body or "").strip().splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()
        parsed_any = True
        if key == "title":
            title = val or title
        elif key == "command":
            command = val
        elif key == "output":
            output = val
        elif key == "status":
            status = val or status
    if not parsed_any:
        output = (body or "").strip()
    return ToolShellBlock(
        title=title,
        command=command,
        output=output,
        status=status,
        block_id=block_id,
        collapsed=False,
    )


if __name__ == "__main__":
    buf = ChatBlockBuffer()
    ops = buf.feed("hello ```py\nx=1\n")
    assert any(o.kind == RenderOpKind.REPLACE_PROSE for o in ops)
    assert any(o.kind == RenderOpKind.INSERT_CODE for o in ops)
    ops2 = buf.feed("```")
    segs = parse_chat_segments(buf.raw)
    assert any(isinstance(s, CodeSegment) and s.complete for s in segs)
    assert prose_char_count("a```b\nc\n```d") == 2  # "ad"
    print("chat_block_parser ok")
