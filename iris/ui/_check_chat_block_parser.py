"""chat_block_parser — 펜스 경계 청크 분할·점진 파싱 자검."""

from __future__ import annotations

from iris.core.chat_block_parser import (
    ChatBlockBuffer,
    CodeSegment,
    ProseSegment,
    RenderOpKind,
    ToolSegment,
    parse_chat_segments,
    prose_char_count,
)


def test_fence_split_across_chunks() -> None:
    buf = ChatBlockBuffer()
    ops1 = buf.feed("앞글 ```py\nprint(")
    assert any(o.kind == RenderOpKind.INSERT_CODE for o in ops1)
    segs1 = parse_chat_segments(buf.raw)
    assert len(segs1) == 2
    assert isinstance(segs1[0], ProseSegment)
    assert isinstance(segs1[1], CodeSegment)
    assert not segs1[1].complete
    assert segs1[1].code == "print("

    ops2 = buf.feed("'hi')\n``")
    segs2 = parse_chat_segments(buf.raw)
    code = next(s for s in segs2 if isinstance(s, CodeSegment))
    assert not code.complete
    assert "'hi')" in code.code
    assert not any(o.kind == RenderOpKind.INSERT_TOOL for o in ops2)

    ops3 = buf.feed("`\n```\n뒷글")
    segs3 = parse_chat_segments(buf.raw)
    code = next(s for s in segs3 if isinstance(s, CodeSegment))
    assert code.complete
    assert "print('hi')" in code.code
    assert prose_char_count(buf.raw) == len("앞글") + len("뒷글")
    assert any(o.kind == RenderOpKind.REPLACE_PROSE for o in ops3)


def test_tool_marker_complete() -> None:
    buf = ChatBlockBuffer()
    start = "IRIS_TOOL_run1_START\ntitle: Tests\ncommand: pytest\noutput: ok\n"
    buf.feed(start)
    assert not any(o.kind == RenderOpKind.INSERT_TOOL for o in buf.feed(""))
    ops = buf.feed("IRIS_TOOL_run1_END\n")
    assert any(o.kind == RenderOpKind.INSERT_TOOL for o in ops)
    tool = next(s for s in parse_chat_segments(buf.raw) if isinstance(s, ToolSegment))
    assert tool.complete
    assert tool.block.title == "Tests"
    assert tool.block.command == "pytest"


def main() -> int:
    test_fence_split_across_chunks()
    test_tool_marker_complete()
    print("chat_block_parser check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
