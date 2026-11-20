"""archify 다이어그램을 채팅 칸 카드에 연다.

Theia에는 HTML 프리뷰가 없어 에디터로 열면 소스만 보인다.
H1 transcript에는 DiagramPart 카드로 착지하고, 상세는 로그–입력 사이 DiagramCard.
"""

from __future__ import annotations

from typing import Any


def open_diagram_preview(
    window: Any,
    html_path: str,
    title: str = "",
    *,
    kind: str = "",
) -> bool:
    """채팅 카드에 HTML을 띄우고 H1에 DiagramPart를 남긴다."""
    chat = getattr(window, "_chat", None)
    show = getattr(chat, "show_diagram", None)
    if not callable(show):
        return False
    if not show(html_path, title):
        return False
    note = getattr(chat, "append_diagram_note", None)
    if callable(note):
        try:
            note(html_path, title, kind=kind)
        except TypeError:
            note(html_path, title)
    return True
