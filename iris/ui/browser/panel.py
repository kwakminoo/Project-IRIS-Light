"""Browser chrome panel — URL bar + back/forward/reload over BrowserSession."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.browser.types import (
    Actor,
    BrowserSnapshot,
    HistoryStep,
    Navigate,
    Reload,
    parse_page_url,
)
from iris.ui.shared.theme_tokens import TOKENS

if TYPE_CHECKING:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    from iris.browser.session import BrowserSession


def _panel_stylesheet() -> str:
    t = TOKENS
    return f"""
    QWidget#IrisBrowserPanel {{
        background: {t.void_black};
    }}
    QLineEdit#IrisBrowserUrl {{
        background: {t.background_secondary};
        color: {t.text_primary};
        border: 1px solid {t.border_subtle};
        border-radius: 4px;
        padding: 4px 8px;
        font-family: {t.font_family};
        font-size: 13px;
    }}
    QPushButton#IrisBrowserNav {{
        background: {t.background_secondary};
        color: {t.text_primary};
        border: 1px solid {t.border_subtle};
        border-radius: 4px;
        padding: 4px 10px;
        font-family: {t.font_family};
        min-width: 36px;
    }}
    QPushButton#IrisBrowserNav:disabled {{
        color: {t.text_secondary};
    }}
    """


class BrowserPanel(QWidget):
    """Human chrome bound to BrowserSnapshot only."""

    snapshot_changed = pyqtSignal(object)
    ide_requested = pyqtSignal()

    def __init__(self, session: BrowserSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IrisBrowserPanel")
        self.setStyleSheet(_panel_stylesheet())
        self._session = session
        self._view: QWebEngineView | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(6)
        self._back = QPushButton("←")
        self._forward = QPushButton("→")
        self._reload = QPushButton("⟳")
        self._ide = QPushButton("IDE")
        self._ide.setToolTip("Return to IDE without closing browser session")
        for btn in (self._back, self._forward, self._reload, self._ide):
            btn.setObjectName("IrisBrowserNav")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url = QLineEdit()
        self._url.setObjectName("IrisBrowserUrl")
        self._url.setPlaceholderText("Enter URL")
        bar.addWidget(self._back)
        bar.addWidget(self._forward)
        bar.addWidget(self._reload)
        bar.addWidget(self._url, 1)
        bar.addWidget(self._ide)
        root.addLayout(bar)

        self._view_slot = QWidget()
        self._view_lay = QVBoxLayout(self._view_slot)
        self._view_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._view_slot, 1)

        self._back.clicked.connect(self._on_back)
        self._forward.clicked.connect(self._on_forward)
        self._reload.clicked.connect(self._on_reload)
        self._ide.clicked.connect(self.ide_requested.emit)
        self._url.returnPressed.connect(self._on_url_submitted)
        self.snapshot_changed.connect(self._apply_snapshot_ui)
        session.add_listener(self.apply_snapshot)
        self.apply_snapshot(session.snapshot())

    def ensure_view(self):
        if self._view is not None:
            return self._view
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.setObjectName("IrisBrowserView")
        view.setAcceptDrops(False)
        view.setStyleSheet(f"background: {TOKENS.void_black};")
        self._view_lay.addWidget(view)
        self._view = view
        return view

    def view(self):
        return self._view

    def release_view(self):
        """Remove view from slot for reparent; keep the same view instance."""
        view = self._view
        if view is None:
            return None
        self._view_lay.removeWidget(view)
        return view

    def place_view(self, view) -> None:
        """Re-add a previously released view into the panel slot."""
        if view is None:
            return
        self._view = view
        if view.parent() is not self._view_slot:
            self._view_lay.addWidget(view)

    def view_in_slot(self) -> bool:
        view = self._view
        return view is not None and view.parent() is self._view_slot

    def apply_snapshot(self, snap: BrowserSnapshot) -> None:
        # Queued across threads when agent execute runs off-UI.
        self.snapshot_changed.emit(snap)

    def _apply_snapshot_ui(self, snap: object) -> None:
        if not isinstance(snap, BrowserSnapshot):
            return
        if snap.url and self._url.text() != snap.url:
            self._url.setText(snap.url)
        self._back.setEnabled(bool(snap.can_go_back))
        self._forward.setEnabled(bool(snap.can_go_forward))
        busy = snap.phase.value in ("busy", "opening")
        self._reload.setEnabled(not busy)

    def shows_same_url(self, url: str) -> bool:
        return self._url.text().rstrip("/") == (url or "").rstrip("/")

    def _on_url_submitted(self) -> None:
        text = self._url.text().strip()
        if not text:
            return
        try:
            url = parse_page_url(text)
        except ValueError:
            return
        self._session.execute(Navigate(url=url, source=Actor.HUMAN))

    def _on_reload(self) -> None:
        self._session.execute(Reload(source=Actor.HUMAN))

    def _on_back(self) -> None:
        self._session.execute(HistoryStep(delta=-1, source=Actor.HUMAN))

    def _on_forward(self) -> None:
        self._session.execute(HistoryStep(delta=1, source=Actor.HUMAN))
