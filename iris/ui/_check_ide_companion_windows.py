"""Companion 복귀 시 orphan 흰 창이 생기지 않는지 자검 (경량).

실행: py -3 -m iris.ui._check_ide_companion_windows
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from iris.ui.drag_tab import DragTab
from iris.ui.top_status_header import TopStatusHeader


def _visible_orphans(main: QWidget) -> list[str]:
    out: list[str] = []
    for w in QApplication.topLevelWidgets():
        if not isinstance(w, QWidget) or w is main:
            continue
        if w.isWindow() and w.isVisible():
            out.append(
                f"{type(w).__name__}:{w.objectName() or '-'} "
                f"title={w.windowTitle()!r} geom={w.geometry()}"
            )
    return out


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Iris Light")

    win = QMainWindow()
    win.setWindowTitle("Iris Light")
    central = QWidget()
    win.setCentralWidget(central)
    lay = QVBoxLayout(central)

    drag = DragTab(win)
    header = TopStatusHeader()
    drag.place_status_rows(header.status_widget(), header.backend_row())
    lay.addWidget(drag)
    win.resize(640, 200)
    win.show()
    app.processEvents()

    # companion enter: status column hide only
    drag.set_ide_companion_active(True)
    app.processEvents()
    mid = _visible_orphans(win)

    # 복귀 — 올바른 경로: status_column show만 (backend_row.show 금지)
    drag.set_ide_companion_active(False)
    app.processEvents()
    after = _visible_orphans(win)

    br = header.backend_row()
    assert br.parentWidget() is not None, "backend_row must be parented to status_block"
    assert not (br.isWindow() and br.isVisible()), "backend_row must not become a window"
    assert not mid and not after, f"orphans mid={mid} after={after}"

    # 회귀: 예전 버그 경로를 쓰면 orphan이 생김을 문서화(실행하지 않음)
    # br.setMaximumHeight(16777215); br.show()  # ← 흰 Iris Light 창

    print("ide_companion orphan-window check ok")
    win.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
