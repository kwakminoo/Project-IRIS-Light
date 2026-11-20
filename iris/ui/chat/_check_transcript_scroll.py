"""G10: H1 body scroll hold / tail-follow (not hidden ChatLog scrollbar)."""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.ui.chat.chat_panel import ChatPanel

_TALL = "# Scroll\n\n" + ("tall line for body scroll height.\n\n" * 50)


def _settle(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_load(view, timeout_ms: int = 15000) -> None:
    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "H1 loadFinished failed"


def _check_scroll_hold_follow(app: QApplication) -> None:
    del app
    panel = ChatPanel()
    panel.resize(640, 420)
    panel.show()
    _settle(50)

    host = panel.transcript()
    view = host.view()
    assert view is not None

    for i in range(6):
        host.append_turn(
            "assistant",
            [TextPart(markdown=_TALL)],
            msg_id=f"scroll-tall-{i}",
        )
    _wait_load(view)
    _settle(300)

    assert hasattr(host, "scroll_to_bottom")
    assert hasattr(host, "scroll_y")
    assert hasattr(host, "set_scroll_y")
    assert hasattr(host, "at_bottom")

    host.scroll_to_bottom()
    _settle(100)
    assert host.at_bottom(threshold=2), f"expected at bottom y={host.scroll_y()}"

    # Force content tall enough that mid scroll is not the tail.
    max_y = 0
    for _ in range(8):
        y = host.scroll_y()
        host.scroll_to_bottom()
        _settle(50)
        max_y = max(max_y, host.scroll_y())
        if max_y > 40:
            break
    assert max_y > 40, f"content not tall enough to hold scroll: max_y={max_y}"

    hold = max(0, max_y // 3)
    host.set_scroll_y(hold)
    _settle(80)
    panel._note_user_log_scroll(hold)
    assert panel._scroll_user_hold, "hold flag not set after mid scroll"
    assert panel._scroll_hold_value == hold
    assert not panel._scroll_follow_tail

    before = host.scroll_y()
    panel._scroll_log_to_bottom()
    _settle(80)
    after = host.scroll_y()
    assert abs(after - hold) <= 4, (
        f"hold must keep Y near {hold}, before={before} after={after}"
    )
    assert not host.at_bottom(threshold=2), f"hold must stay off bottom: y={after}"

    host.scroll_to_bottom()
    _settle(80)
    panel._note_user_log_scroll(host.scroll_y())
    assert panel._scroll_follow_tail
    assert not panel._scroll_user_hold

    # Grow content while following — helper must chase the new max.
    host.append_turn(
        "assistant",
        [TextPart(markdown=_TALL)],
        msg_id="scroll-tall-follow",
    )
    _settle(200)
    panel._scroll_log_to_bottom()
    _settle(100)
    assert host.at_bottom(threshold=2), (
        f"follow_tail must move to bottom: y={host.scroll_y()}"
    )

    print("transcript_scroll hold/follow ok", {"hold": hold, "max_y": max_y})
    panel.close()


def _check_dom_patch_preserves_hold(app: QApplication) -> None:
    """After page-ready innerHTML patch, hold must not look like a user scroll."""
    del app
    panel = ChatPanel()
    panel.resize(640, 420)
    panel.show()
    _settle(50)

    host = panel.transcript()
    view = host.view()
    assert view is not None

    # First paint + loadFinished before more turns (stay on patch path).
    host.append_turn(
        "assistant",
        [TextPart(markdown=_TALL)],
        msg_id="patch-tall-0",
    )
    _wait_load(view)
    _settle(100)
    assert host._page_ready, "page must be ready so append uses DOM patch"

    for i in range(1, 6):
        host.append_turn(
            "assistant",
            [TextPart(markdown=_TALL)],
            msg_id=f"patch-tall-{i}",
        )
    _settle(300)

    host.scroll_to_bottom()
    _settle(80)
    assert host._page_ready, "programmatic scroll must not clear page_ready"
    max_y = host.scroll_y()
    assert max_y > 40, f"content not tall enough: max_y={max_y}"

    hold = max(0, max_y // 3)
    host.set_scroll_y(hold)
    _settle(80)
    assert host._page_ready, "set_scroll_y must not clear page_ready"
    panel._note_user_log_scroll(hold)
    assert panel._scroll_user_hold, "precondition: mid hold"
    assert panel._scroll_hold_value == hold
    assert not panel._scroll_follow_tail

    # Programmatic full-DOM land (stream end re-land path).
    host.append_turn(
        "assistant",
        [TextPart(markdown=_TALL)],
        msg_id="patch-after-ready",
    )
    _settle(300)

    assert host._page_ready, "re-land must stay on DOM patch (not setHtml)"
    assert panel._scroll_user_hold, (
        "DOM patch must not flip hold off as if the user scrolled"
    )
    assert not panel._scroll_follow_tail, (
        "DOM patch must not start follow_tail from a patch scroll notify"
    )
    assert panel._scroll_hold_value == hold, (
        f"hold value must stay {hold}, got {panel._scroll_hold_value}"
    )
    after = host.scroll_y()
    assert abs(after - hold) <= 8, (
        f"held Y must survive DOM patch: want~{hold} after={after}"
    )

    print(
        "transcript_scroll dom_patch hold ok",
        {"hold": hold, "after": after},
    )
    panel.close()


def main() -> int:
    app = QApplication.instance() or _APP
    _check_scroll_hold_follow(app)
    _check_dom_patch_preserves_hold(app)
    print("transcript_scroll ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
