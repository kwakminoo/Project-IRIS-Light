"""H1 history ToolPart lands as Cursor-style shell card (not muted prose).

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_transcript_tool_part_history
"""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import ToolPart, parse_parts, parts_to_jsonable
from iris.ui.chat.chat_panel import ChatPanel


def _h1_html(panel: ChatPanel) -> str:
    return panel.transcript()._transcript_inner_html()


def _assert_shell_chrome(html: str, *, title: str, needle: str) -> None:
    assert title in html, html[:800]
    assert needle in html, html[:800]
    assert "&gt;_" in html or ">_" in html, html[:800]
    assert "iris-collapse://" in html, html[:800]
    assert "part-muted" not in html or title in html, html[:800]


def _check_expanded_tool_part(panel: ChatPanel) -> None:
    host = panel.transcript()
    host.append_turn(
        "assistant",
        [
            ToolPart(
                name="Run tests",
                command="pytest -q",
                output="3 passed",
                status="ok",
                block_id="hist-tool-1",
            )
        ],
        msg_id="tool-shell-hist-tool-1",
    )
    html = _h1_html(panel)
    _assert_shell_chrome(html, title="Run tests", needle="pytest -q")
    assert "성공" in html, html[:800]
    assert "3 passed" in html, html[:800]
    plain = panel._log.toPlainText()
    assert "Run tests" not in plain, plain


def _check_legacy_tool_part_card(panel: ChatPanel) -> None:
    host = panel.transcript()
    host.clear()
    host.append_turn(
        "assistant",
        [ToolPart(name="wiki.search", detail="q=iris")],
        msg_id="legacy-tool-1",
    )
    html = _h1_html(panel)
    assert "wiki.search" in html, html[:800]
    assert "q=iris" in html, html[:800]
    assert "&gt;_" in html or ">_" in html, html[:800]
    assert "part-muted" not in html, html[:800]


def _check_serde_round_trip_card(panel: ChatPanel) -> None:
    host = panel.transcript()
    host.clear()
    original = [
        ToolPart(
            name="Shell",
            command="echo hi",
            output="hi",
            status="ok",
            block_id="serde-1",
        )
    ]
    again = parse_parts(parts_to_jsonable(original))
    host.append_turn("assistant", again, msg_id="tool-shell-serde-1")
    html = _h1_html(panel)
    _assert_shell_chrome(html, title="Shell", needle="echo hi")
    assert "hi" in html, html[:800]


def main() -> int:
    _ = QApplication.instance() or _APP
    panel = ChatPanel()
    _check_expanded_tool_part(panel)
    _check_legacy_tool_part_card(panel)
    _check_serde_round_trip_card(panel)
    print("transcript_tool_part_history ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
