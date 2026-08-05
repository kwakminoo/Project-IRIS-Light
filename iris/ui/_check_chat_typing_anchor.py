"""타이핑 중 화면 고정 자검 — 답변 시작 줄에서 멈추되 타이핑 효과는 유지."""

from __future__ import annotations

import os
import sys

# offscreen — CI/헤드리스에서도 Qt 위젯 생성 가능
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel

LONG_ANSWER = "아이리스가 길게 설명하는 문장입니다. " * 60


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    panel.resize(420, 320)
    panel.show()
    app.processEvents()

    # 스크롤이 생기도록 이전 대화 채우기
    for i in range(12):
        panel.append_message_instant("나", f"이전 질문 {i}")
        panel.append_message_instant("Iris", f"이전 답변 {i}")
    app.processEvents()
    bar = panel._log.verticalScrollBar()
    assert bar.maximum() > 0, "테스트 전제: 로그가 스크롤 가능해야 함"

    panel.append_message_typed("Iris", LONG_ANSWER, speech_sync=False)
    app.processEvents()  # 앵커 캡처(singleShot) 처리
    anchor = panel._typing_anchor_y
    body_start = panel._typing_body_start
    assert anchor is not None, "타이핑 시작 시 앵커가 잡혀야 함"
    assert body_start is not None

    lengths: list[int] = []
    for _ in range(5000):
        if not panel._typing_text:
            break
        panel._type_next_chunk()
        app.processEvents()
        if panel._typing_text:  # 마지막 틱은 버퍼를 비우므로 제외
            lengths.append(panel._typing_index)
    else:
        raise AssertionError("타이핑이 끝나지 않음")

    # 1) 타이핑 효과 유지 — 여러 틱에 걸쳐 조금씩 늘어났는가
    assert len(lengths) > 3, f"한 번에 다 찍힘(타이핑 효과 소실): {lengths}"
    assert all(b > a for a, b in zip(lengths, lengths[1:])), lengths

    # 2) 화면은 답변 시작 줄에 멈춰 있는가 (맨 아래로 따라가지 않음)
    assert bar.maximum() > anchor, (bar.maximum(), anchor)
    assert bar.value() == anchor, (bar.value(), anchor)
    assert bar.value() < bar.maximum(), "맨 아래까지 따라 내려감"

    # 3) 답변 첫 줄이 화면 안(상단)에 보이는가
    cursor = panel._log.textCursor()
    cursor.setPosition(body_start)
    top = panel._log.cursorRect(cursor).top()
    assert 0 <= top < panel._log.viewport().height(), top

    # 4) 다음 사용자 메시지에서는 다시 맨 아래로
    panel.append_message_instant("나", "다음 질문")
    app.processEvents()
    assert panel._typing_anchor_y is None
    assert bar.value() == bar.maximum(), (bar.value(), bar.maximum())

    print("chat typing anchor ok", f"anchor={anchor}", f"max={bar.maximum()}", f"ticks={len(lengths)}")
    _check_stream(app, panel)
    return 0


def _check_stream(app: QApplication, panel: ChatPanel) -> None:
    """스트리밍(청크 즉시 표시) 답변도 시작 줄에서 멈추는지."""
    bar = panel._log.verticalScrollBar()
    panel.begin_stream_message("Iris", speech_sync=False)
    app.processEvents()
    anchor = panel._typing_anchor_y
    assert anchor is not None
    for _ in range(40):
        panel.append_stream_chunk("스트리밍으로 들어오는 답변 조각입니다. ")
        app.processEvents()
    panel.end_stream_message()
    app.processEvents()
    assert bar.maximum() > anchor, (bar.maximum(), anchor)
    assert bar.value() == anchor, (bar.value(), anchor)
    print("chat stream anchor ok", f"anchor={anchor}", f"max={bar.maximum()}")


if __name__ == "__main__":
    raise SystemExit(main())
