"""H1 lands Cursor-style ToolShell cards; ghost `_log` stays empty.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_transcript_tool_shell
"""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat.chat_blocks import collapse_anchor_for
from iris.ui.chat.chat_panel import ChatPanel


def _h1_html(panel: ChatPanel) -> str:
    return panel.transcript()._transcript_inner_html()


def _check_insert_lands_on_h1(panel: ChatPanel) -> None:
    bid = panel.insert_tool_block(
        title="Run tests",
        command="pytest -q",
        output="3 passed",
        status="ok",
        block_id="tool-h1-1",
    )
    assert bid == "tool-h1-1", bid
    assert bid in panel._tool_blocks, sorted(panel._tool_blocks)
    html = _h1_html(panel)
    assert "Run tests" in html, html[:800]
    assert "pytest -q" in html, html[:800]
    assert "성공" in html, html[:800]
    assert "&gt;_" in html or ">_" in html, html[:800]
    assert "iris-collapse://" in html, html[:800]
    assert collapse_anchor_for(bid) in html or f"iris-collapse://{bid}" in html, html[:800]
    plain = panel._log.toPlainText()
    assert "Run tests" not in plain, plain
    assert "pytest -q" not in plain, plain
    assert bid not in getattr(panel._log, "_tool_blocks", {}), panel._log._tool_blocks


def _check_collapse_toggles_h1(panel: ChatPanel) -> None:
    bid = "tool-h1-1"
    block = panel._tool_blocks[bid]
    assert block.collapsed is False
    before = _h1_html(panel)
    assert "▼" in before, before[:800]
    panel._on_h1_anchor(collapse_anchor_for(bid))
    after = panel._tool_blocks[bid]
    assert after.collapsed is True, after
    html = _h1_html(panel)
    assert "▶" in html, html[:800]
    assert "display:none" in html or 'display:none' in html.replace(" ", ""), html[:800]
    panel._on_h1_anchor(collapse_anchor_for(bid))
    assert panel._tool_blocks[bid].collapsed is False
    assert "▼" in _h1_html(panel)


def main() -> int:
    _ = QApplication.instance() or _APP
    panel = ChatPanel()
    _check_insert_lands_on_h1(panel)
    _check_collapse_toggles_h1(panel)
    print("transcript_tool_shell ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
