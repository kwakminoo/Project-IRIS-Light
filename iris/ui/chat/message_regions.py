"""채팅 로그에서 답변 영역 찾기 — 본문 클릭으로 전체보기에 들어가기 위한 판정.

채팅 로그는 단일 QTextDocument라 메시지별 위젯이 없다. 그래서 답변의 시작은
화자 이름에 심는 named anchor(`iris-msg-<id>`), 끝은 기존 재생 링크
(`iris-tts://<id>`)로 표시하고, 클릭 시점에 문서를 훑어 범위를 되찾는다.

실측 확인: 이 두 표시는 QTextDocument의 toHtml/setHtml 왕복에서 살아남는다.
반면 블록 포맷 커스텀 프로퍼티는 유실되고 문자 위치는 밀리므로
(set_speaker_status·STT 치환이 setHtml을 쓴다) 저장해 둔 위치는 쓰지 않는다.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from PyQt6.QtGui import QTextDocument

MSG_ANCHOR_PREFIX = "iris-msg-"
TTS_SCHEME = "iris-tts://"

# 화면에서 한 번에 읽기 어려운 답변만 클릭 대상으로 삼는다.
READING_VIEWPORT_RATIO = 0.85
READING_MIN_CHARS = 400


@dataclass(frozen=True)
class MessageRegion:
    """문서 안 한 답변의 문자 범위."""

    msg_id: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    def contains(self, position: int) -> bool:
        return self.start <= position <= self.end


def message_anchor_name(msg_id: str) -> str:
    return f"{MSG_ANCHOR_PREFIX}{(msg_id or '').strip()}"


def parse_message_anchor_name(name: str) -> str | None:
    raw = (name or "").strip()
    if not raw.startswith(MSG_ANCHOR_PREFIX):
        return None
    msg_id = raw[len(MSG_ANCHOR_PREFIX) :].strip()
    return msg_id or None


def speaker_prefix_html(who: str, msg_id: str = "") -> str:
    """`Iris: ` 접두사. msg_id가 있으면 답변 시작점 표시를 함께 심는다.

    href가 아니라 name 앵커라서 링크 색·밑줄·anchorAt 동작에 영향이 없다.
    """
    name = html.escape(who or "")
    key = (msg_id or "").strip()
    if not key:
        return f"<b>{name}</b>: "
    anchor = html.escape(message_anchor_name(key), quote=True)
    return f'<a name="{anchor}"><b>{name}</b></a>: '


def scan_message_regions(document: QTextDocument) -> list[MessageRegion]:
    """문서 전체를 훑어 (시작 앵커, 재생 링크) 쌍으로 답변 범위를 만든다."""
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                for name in fmt.anchorNames():
                    msg_id = parse_message_anchor_name(name)
                    if msg_id and msg_id not in starts:
                        starts[msg_id] = fragment.position()
                href = fmt.anchorHref()
                if href.startswith(TTS_SCHEME):
                    tts_id = href[len(TTS_SCHEME) :].strip()
                    if tts_id and tts_id not in ends:
                        ends[tts_id] = fragment.position()
            iterator += 1
        block = block.next()

    regions: list[MessageRegion] = []
    for msg_id, start in starts.items():
        end = ends.get(msg_id)
        if end is None or end < start:
            continue
        regions.append(MessageRegion(msg_id, start, end))
    regions.sort(key=lambda region: region.start)
    return regions


def region_at_position(regions: list[MessageRegion], position: int) -> MessageRegion | None:
    for region in regions:
        if region.contains(position):
            return region
    return None


def region_rendered_height(document: QTextDocument, region: MessageRegion) -> float:
    """답변이 실제로 차지하는 픽셀 높이 (표·코드 카드 포함)."""
    layout = document.documentLayout()
    if layout is None:
        return 0.0
    block = document.findBlock(region.start)
    last = document.findBlock(region.end)
    if not block.isValid():
        return 0.0
    last_number = last.blockNumber() if last.isValid() else document.blockCount() - 1
    total = 0.0
    while block.isValid():
        total += layout.blockBoundingRect(block).height()
        if block.blockNumber() >= last_number:
            break
        block = block.next()
    return total


def region_opens_reading_view(
    *,
    text_chars: int,
    rendered_height: float,
    viewport_height: int,
) -> bool:
    """한 화면에 담기 어려운 긴 답변만 True."""
    if text_chars < READING_MIN_CHARS:
        return False
    if viewport_height <= 0:
        return False
    return rendered_height >= viewport_height * READING_VIEWPORT_RATIO


if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QTextEdit

    from iris.ui.chat.chat_renderer import render_iris_message

    assert parse_message_anchor_name(message_anchor_name("m3")) == "m3"
    assert parse_message_anchor_name("iris-tts://m3") is None
    assert "<b>You</b>: " == speaker_prefix_html("You")
    assert 'name="iris-msg-m3"' in speaker_prefix_html("Iris", "m3")

    app = QApplication.instance() or QApplication(sys.argv)
    edit = QTextEdit()
    edit.resize(600, 400)
    edit.show()
    app.processEvents()

    cursor = edit.textCursor()
    cursor.insertHtml(speaker_prefix_html("You", ""))
    cursor.insertHtml(render_iris_message("사용자 질문입니다."))
    cursor.insertBlock()
    cursor.insertHtml(speaker_prefix_html("Iris", "m1"))
    body_start = cursor.position()
    cursor.insertHtml(render_iris_message("답변 본문 " * 200))
    cursor.insertHtml('<a href="iris-tts://m1">[재생]</a>')
    app.processEvents()

    regions = scan_message_regions(edit.document())
    assert len(regions) == 1, regions
    assert regions[0].msg_id == "m1"
    assert regions[0].start < body_start <= regions[0].end

    # 사용자 메시지 위치는 어떤 답변에도 속하지 않는다
    assert region_at_position(regions, 2) is None
    assert region_at_position(regions, body_start + 5) is regions[0]

    height = region_rendered_height(edit.document(), regions[0])
    assert height > 0
    assert region_opens_reading_view(
        text_chars=regions[0].length, rendered_height=height, viewport_height=200
    )
    assert not region_opens_reading_view(
        text_chars=10, rendered_height=height, viewport_height=200
    )
    assert not region_opens_reading_view(
        text_chars=regions[0].length, rendered_height=10.0, viewport_height=800
    )

    # setHtml 왕복 후에도 범위를 되찾을 수 있어야 한다
    edit.setHtml(edit.toHtml())
    again = scan_message_regions(edit.document())
    assert len(again) == 1 and again[0].msg_id == "m1", again
    print("message_regions ok", regions[0], f"h={height:.0f}")
