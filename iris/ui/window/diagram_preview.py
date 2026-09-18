"""archify 다이어그램 HTML 표시.

Theia에는 HTML 프리뷰 확장(`@theia/preview`·`mini-browser`)이 없어 에디터로 열면
소스만 보인다. 그래서 표시는 IRIS 쪽 `QWebEngineView` 1개를 재사용한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl


def open_diagram_preview(window: Any, html_path: str) -> bool:
    """다이어그램 HTML을 프리뷰 창에 띄운다. 파일이 없으면 False.

    qt-webengine-bootstrap.mdc: WebEngine 뷰는 첫 사용 시에만 생성한다.
    pyqt-orphan-windows.mdc: 부모를 반드시 넘긴다 (빈 「Iris Light」 창 방지).
    """
    path = Path(html_path)
    if not path.is_file():
        return False
    view = getattr(window, "_diagram_preview", None)
    if view is None:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(window)
        view.setWindowFlag(Qt.WindowType.Window, True)
        view.setWindowTitle("IRIS Diagram")
        view.resize(1280, 820)
        window._diagram_preview = view
    view.load(QUrl.fromLocalFile(str(path.resolve())))
    view.show()
    view.raise_()
    return True
