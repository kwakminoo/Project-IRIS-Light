"""실행 중인 창 목록 — HUD 스타일 좌측 사이드바."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.automation.window_controller import (
    WindowInfo,
    close_window_by_hwnd,
    focus_and_place,
    focus_window_by_hwnd,
    list_visible_windows,
)
from iris.ui.section_header import apply_section_panel_layout, make_section_header
from iris.ui.theme_tokens import TOKENS

_REFRESH_MS = 2_500
_MAX_ITEMS = 30


class WindowListPanel(QWidget):
    """메인 창 좌측에 통합되는 실행 창 목록 — 사이버스페이스 HUD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowListPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        apply_section_panel_layout(root)

        root.addWidget(
            make_section_header("RUNNING WINDOWS", title_object_name="SidebarTitle")
        )

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._inner = QWidget()
        self._inner.setObjectName("SidebarInner")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(0)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        self._prev_signature: tuple = ()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _refresh(self) -> None:
        try:
            wins = list_visible_windows()
        except Exception:
            wins = []
        wins = wins[:_MAX_ITEMS]

        signature = tuple((w.hwnd, w.title) for w in wins)
        if signature == self._prev_signature:
            return
        self._prev_signature = signature

        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not wins:
            hint = QLabel("— no active windows")
            hint.setStyleSheet(
                f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_micro};"
                " padding: 8px 4px; background: transparent;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for info in wins:
                self._inner_lay.addWidget(_make_row(info, self._on_focus, self._on_close))

        self._inner_lay.addStretch(1)

    def _on_focus(self, info: WindowInfo) -> None:
        ok = False
        if info.hwnd:
            ok = focus_window_by_hwnd(info.hwnd)
        if not ok:
            try:
                focus_and_place(info.title, info.left, info.top, info.width, info.height)
            except Exception:
                pass

    def _on_close(self, info: WindowInfo) -> None:
        if info.hwnd:
            close_window_by_hwnd(info.hwnd)
            QTimer.singleShot(300, self._refresh)


def _make_row(info: WindowInfo, on_focus, on_close) -> QFrame:
    """HUD 리스트 행 — [제목] [×]"""
    fr = QFrame()
    fr.setObjectName("HudWindowRow")

    h = QHBoxLayout(fr)
    h.setContentsMargins(2, 2, 2, 2)
    h.setSpacing(2)

    display = info.title if len(info.title) <= 24 else info.title[:22] + "…"
    btn = QPushButton(display)
    btn.setToolTip(info.title)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    btn.setStyleSheet(
        f"""
        QPushButton {{
            text-align: left;
            padding: 4px 6px;
            background: transparent;
            border: none;
            color: {TOKENS.text_secondary};
            font-size: {TOKENS.font_size_micro};
        }}
        QPushButton:hover {{
            color: {TOKENS.neon_cyan};
        }}
        """
    )
    btn.clicked.connect(lambda _=False, i=info: on_focus(i))
    h.addWidget(btn, 1)

    x = QPushButton("×")
    x.setFixedSize(20, 20)
    x.setCursor(Qt.CursorShape.PointingHandCursor)
    x.setToolTip(f"창 닫기: {info.title}")
    x.setStyleSheet(
        f"""
        QPushButton {{
            background: transparent;
            border: none;
            color: {TOKENS.text_muted};
            font-size: 14px;
        }}
        QPushButton:hover {{ color: {TOKENS.error}; }}
        """
    )
    x.clicked.connect(lambda _=False, i=info: on_close(i))
    h.addWidget(x, 0)

    return fr
