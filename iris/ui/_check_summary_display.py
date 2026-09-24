"""연번 10 — Iris 답변 화면은 요약만. 원문·사용자 메시지·풀 렌더는 유지."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.system.project_ops import extract_first_code_block
from iris.ui.chat.chat_display import assistant_visible_text
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_renderer import render_iris_message, render_user_message

_FENCE = "```"


def _check_text() -> None:
    plain = "요청한 파일을 IDE에 열었습니다."
    assert assistant_visible_text(plain, streaming=False) == plain

    err = "파일을 열지 못했습니다: 권한 없음"
    assert assistant_visible_text(err, streaming=False) == err

    bare = "IDE에 gugudan.py 를 열었습니다."
    assert assistant_visible_text(bare, streaming=False) == bare

    link = "참고 [docs](https://example.com/a/b.py) 입니다."
    linked = assistant_visible_text(link, streaming=False)
    assert "https://example.com/a/b.py" in linked
    assert "참고" in linked and "입니다." in linked

    mixed = (
        "요청한 스크립트입니다.\n\n"
        f"{_FENCE}python\nprint('secret_token')\n{_FENCE}\n\n"
        "실행은 IDE 통합 터미널에서 합니다."
    )
    shown = assistant_visible_text(mixed, streaming=False)
    assert "secret_token" not in shown
    assert "요청한 스크립트입니다." in shown
    assert "실행은 IDE 통합 터미널에서 합니다." in shown
    assert "작업 완료" not in shown
    assert extract_first_code_block(mixed), "원문 펜스 감지가 깨짐"
    assert "secret_token" in render_iris_message(mixed)

    multi = f"첫째.\n{_FENCE}py\na=1\n{_FENCE}\n둘째.\n{_FENCE}py\nb=2\n{_FENCE}\n셋째."
    multi_shown = assistant_visible_text(multi, streaming=False)
    assert "a=1" not in multi_shown and "b=2" not in multi_shown
    assert "첫째." in multi_shown and "둘째." in multi_shown and "셋째." in multi_shown

    assert assistant_visible_text(f"{_FENCE}python\nprint(1)\n{_FENCE}", streaming=False) == ""

    path = "경로는 C:/Users/kwakm/Desktop/Iris_adt.py 입니다"
    pathed = assistant_visible_text(path, streaming=False)
    assert "Users" not in pathed and "kwakm" not in pathed
    assert "Iris_adt.py" in pathed and "입니다" in pathed

    folder = "폴더 C:/Users/kwakm 입니다"
    folded = assistant_visible_text(folder, streaming=False)
    assert "Users" not in folded and "kwakm" not in folded
    assert "폴더" in folded and "입니다" in folded and "작업 폴더" in folded

    rel = "edit iris/ui/chat/chat_renderer.py now"
    rel_shown = assistant_visible_text(rel, streaming=False)
    assert "iris/ui/chat" not in rel_shown
    assert "chat_renderer.py" in rel_shown and "edit" in rel_shown and "now" in rel_shown

    assert "and/or" in assistant_visible_text("use and/or now", streaming=False)

    tool = (
        "실행했습니다.\n"
        "IRIS_TOOL_run1_START\n"
        "title: Shell\ncommand: pytest -q\noutput: TRACE_TOKEN\n"
        "IRIS_TOOL_run1_END\n"
        "실패하면 로그를 보세요."
    )
    tool_shown = assistant_visible_text(tool, streaming=False)
    assert "TRACE_TOKEN" not in tool_shown and "pytest" not in tool_shown
    assert "실행했습니다." in tool_shown and "실패하면 로그를 보세요." in tool_shown

    buf = ""
    for chunk in ("파일을 ", "C:/Users/", "kwakm/Desktop/", "Iris_adt.py", " 에 썼습니다."):
        buf += chunk
        snap = assistant_visible_text(buf, streaming=True)
        assert "Users" not in snap and "kwakm" not in snap and "C:" not in snap, snap
    done = assistant_visible_text(buf, streaming=False)
    assert "Iris_adt.py" in done and "썼습니다" in done and "Users" not in done

    fence_buf = ""
    for chunk in (
        "설명입니다.\n",
        "``",
        "`python\nprint('secret_token')\n",
        f"{_FENCE}\n",
        "끝입니다.",
    ):
        fence_buf += chunk
        snap = assistant_visible_text(fence_buf, streaming=True)
        assert "secret_token" not in snap, snap
    fence_done = assistant_visible_text(fence_buf, streaming=False)
    assert "설명입니다." in fence_done and "끝입니다." in fence_done
    assert "secret_token" not in fence_done

    unclosed = "설명입니다.\n```python\nprint('secret_token')"
    assert "secret_token" not in assistant_visible_text(unclosed, streaming=True)
    assert "secret_token" not in assistant_visible_text(unclosed, streaming=False)
    assert "설명입니다." in assistant_visible_text(unclosed, streaming=False)

    partial_tool = assistant_visible_text("실행했습니다. IRIS_TOO", streaming=True)
    assert "IRIS_TOO" not in partial_tool
    assert "실행했습니다." in partial_tool

    cancelled = "설명 C:/Users/kwa"
    cancelled_shown = assistant_visible_text(cancelled, streaming=False)
    assert "Users" not in cancelled_shown and "C:" not in cancelled_shown
    assert "설명" in cancelled_shown
    assert "작업 완료" not in cancelled_shown


def _check_panel(app: QApplication) -> None:
    panel = ChatPanel()
    panel.resize(480, 360)
    panel.show()
    app.processEvents()

    user_code = f"{_FENCE}py\nkeep_user_token = 1\n{_FENCE}"
    panel.append_message_instant("You", user_code)
    app.processEvents()
    assert "keep_user_token" in panel._log.toPlainText()
    assert "keep_user_token" in render_user_message(user_code)

    panel.begin_stream_message("Iris", speech_sync=False)
    buf = ""
    for chunk in ("요약입니다.\n", "``", "`py\nsecret_stream()\n", f"{_FENCE}\n"):
        buf += chunk
        panel.append_stream_chunk(chunk)
        panel._flush_stream_ui()
        app.processEvents()
        assert "secret_stream" not in panel._log.toPlainText(), panel._log.toPlainText()
    panel.end_stream_message(buf + "여기까지입니다.")
    app.processEvents()
    plain = panel._log.toPlainText()
    assert "secret_stream" not in plain
    assert "요약입니다." in plain and "여기까지입니다." in plain
    assert "작업 완료" not in plain
    stored = panel.message_body("last")
    assert "secret_stream" in stored, "화면용 텍스트가 원문 저장을 덮어씀"

    panel.append_message_instant("Iris", f"{_FENCE}py\nonly_code()\n{_FENCE}")
    app.processEvents()
    assert "only_code" not in panel._log.toPlainText()
    assert "작업 완료" not in panel._log.toPlainText()

    panel.restore_messages(
        [
            {"role": "user", "content": "다시 보여줘"},
            {
                "role": "assistant",
                "content": (
                    "기록 요약입니다.\n"
                    f"{_FENCE}py\nhistory_secret()\n{_FENCE}\n"
                    "경로 C:/Users/a/b.py 입니다"
                ),
            },
        ]
    )
    app.processEvents()
    replay = panel._log.toPlainText()
    assert "기록 요약입니다." in replay and "입니다" in replay
    assert "history_secret" not in replay and "Users" not in replay
    assert "b.py" in replay

    panel.begin_stream_message("Iris", speech_sync=False)
    panel.append_stream_chunk("오류 전 설명\n```py\nprint(")
    panel._flush_stream_ui()
    panel.end_stream_message(None)
    app.processEvents()
    assert "print" not in panel._log.toPlainText()
    assert "오류 전 설명" in panel._log.toPlainText()
    panel.append_message_instant("Iris", "Hermes 오류: timeout")
    app.processEvents()
    assert "Hermes 오류: timeout" in panel._log.toPlainText()


def main() -> int:
    _check_text()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_panel(app)
    print("summary display ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
