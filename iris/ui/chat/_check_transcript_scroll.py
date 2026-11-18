"""H1 DOM patch must keep body.scrollTop (mute+restore); hold flags must not flip."""

from __future__ import annotations

import json
import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.ui.chat.chat_panel import ChatPanel

_TALL = "# Scroll\n\n" + ("tall line for body scroll height.\n\n" * 50)

_SCROLL_PROBE = (
    "(function(){"
    "var b=document.body;if(!b)return JSON.stringify({y:0,max:0});"
    "var max=Math.max(0,(b.scrollHeight||0)-(b.clientHeight||0));"
    "return JSON.stringify({y:Math.round(b.scrollTop||0),max:max});"
    "})();"
)


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


def _run_js(view, script: str, timeout_ms: int = 10000):
    box: dict = {"raw": None, "done": False}
    loop = QEventLoop()

    def _cb(raw) -> None:
        box["raw"] = raw
        box["done"] = True
        loop.quit()

    view.page().runJavaScript(script, _cb)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not box["done"]:
        loop.exec()
    return box["raw"]


def _scroll_state(view) -> dict:
    raw = _run_js(view, _SCROLL_PROBE)
    assert raw is not None, "scroll probe returned None"
    data = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(data, dict), data
    return data


def _set_scroll_y(view, y: int) -> None:
    _run_js(
        view,
        "(function(){"
        f"var b=document.body;if(!b)return;"
        f"b.scrollTop={int(y)};"
        "})();",
    )


def _check_failed_load_keeps_ready(app: QApplication) -> None:
    del app
    panel = ChatPanel()
    panel.resize(640, 420)
    panel.show()
    _settle(50)
    host = panel.transcript()
    view = host.view()
    assert view is not None
    host.append_turn(
        "assistant",
        [TextPart(markdown=_TALL)],
        msg_id="ready-0",
    )
    _wait_load(view)
    assert host._page_ready
    host._on_page_load_finished(False)
    assert host._page_ready, "failed loadFinished must not clear _page_ready"
    print("transcript_scroll loadFinished(False) keeps ready ok")
    panel.close()


def _check_dom_patch_preserves_hold(app: QApplication) -> None:
    """After page-ready innerHTML patch, held Y and hold flags must survive."""
    del app
    panel = ChatPanel()
    panel.resize(640, 420)
    panel.show()
    _settle(50)

    host = panel.transcript()
    view = host.view()
    assert view is not None

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

    state = _scroll_state(view)
    max_y = int(state.get("max") or 0)
    assert max_y > 40, f"content not tall enough: max_y={max_y}"
    _set_scroll_y(view, max_y)
    _settle(80)

    hold = max(0, max_y // 3)
    _set_scroll_y(view, hold)
    _settle(80)
    before = _scroll_state(view)
    assert abs(int(before.get("y") or 0) - hold) <= 8, before

    panel._scroll_follow_tail = False
    panel._scroll_user_hold = True
    panel._scroll_hold_value = hold

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
    after = _scroll_state(view)
    after_y = int(after.get("y") or 0)
    assert abs(after_y - hold) <= 8, (
        f"held Y must survive DOM patch: want~{hold} after={after_y}"
    )

    print(
        "transcript_scroll dom_patch hold ok",
        {"hold": hold, "after": after_y},
    )
    panel.close()


def main() -> int:
    app = QApplication.instance() or _APP
    _check_failed_load_keeps_ready(app)
    _check_dom_patch_preserves_hold(app)
    print("transcript_scroll ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
