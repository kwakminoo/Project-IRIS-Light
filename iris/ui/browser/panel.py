from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTabBar,
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
    QTabBar#IrisBrowserTabs {{
        background: {t.void_black};
        color: {t.text_primary};
    }}
    QTabBar#IrisBrowserTabs::tab {{
        background: {t.background_secondary};
        color: {t.text_primary};
        border: 1px solid {t.border_subtle};
        padding: 4px 10px;
        min-width: 80px;
    }}
    QTabBar#IrisBrowserTabs::tab:selected {{
        border-bottom: 1px solid {t.void_black};
    }}
    """


_SHARED_PANEL: BrowserPanel | None = None


def get_shared_browser_panel(session: "BrowserSession") -> BrowserPanel:
    global _SHARED_PANEL
    if _SHARED_PANEL is None:
        _SHARED_PANEL = BrowserPanel(session)
    return _SHARED_PANEL


def reset_shared_browser_panel_for_tests() -> None:
    global _SHARED_PANEL
    _SHARED_PANEL = None


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
        self._pages: list[object] = []
        self._switching_tab = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(8, 4, 8, 0)
        tab_row.setSpacing(4)
        self._tabs = QTabBar()
        self._tabs.setObjectName("IrisBrowserTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setTabsClosable(True)
        self._tabs.setExpanding(False)
        self._tabs.setDrawBase(False)
        self._tabs.setMovable(True)
        self._new_tab = QPushButton("+")
        self._new_tab.setObjectName("IrisBrowserNav")
        self._new_tab.setToolTip("New tab")
        self._new_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ide_btn = QPushButton("IDE")
        self._ide_btn.setObjectName("IrisBrowserNav")
        self._ide_btn.setToolTip("Return to IRIS IDE")
        self._ide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tab_row.addWidget(self._tabs, 1)
        tab_row.addWidget(self._new_tab)
        tab_row.addWidget(self._ide_btn)
        root.addLayout(tab_row)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(6)
        self._back = QPushButton("←")
        self._forward = QPushButton("→")
        self._reload = QPushButton("⟳")
        for btn in (self._back, self._forward, self._reload):
            btn.setObjectName("IrisBrowserNav")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url = QLineEdit()
        self._url.setObjectName("IrisBrowserUrl")
        self._url.setPlaceholderText("Enter URL")
        bar.addWidget(self._back)
        bar.addWidget(self._forward)
        bar.addWidget(self._reload)
        bar.addWidget(self._url, 1)
        root.addLayout(bar)

        self._view_slot = QWidget()
        self._view_lay = QVBoxLayout(self._view_slot)
        self._view_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._view_slot, 1)

        self._back.clicked.connect(self._on_back)
        self._forward.clicked.connect(self._on_forward)
        self._reload.clicked.connect(self._on_reload)
        self._url.returnPressed.connect(self._on_url_submitted)
        self._new_tab.clicked.connect(self._on_new_tab)
        self._ide_btn.clicked.connect(self.ide_requested.emit)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)
        self.snapshot_changed.connect(self._apply_snapshot_ui)
        session.add_listener(self.apply_snapshot)
        self.apply_snapshot(session.snapshot())

    def ensure_view(self):
        if self._view is not None:
            return self._view
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

        ensure_qt_webengine_ready()
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        from iris.ui.browser.webengine_setup import configure_browser_view

        view = QWebEngineView()
        view.setObjectName("IrisBrowserView")
        view.setAcceptDrops(False)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setStyleSheet(f"background: {TOKENS.void_black};")
        configure_browser_view(view, on_create_window=self._adopt_popup)
        self._view_lay.addWidget(view)
        self._view = view
        page = view.page()
        self._pages = [page]
        self._hook_page(page)
        if self._tabs.count() == 0:
            self._tabs.addTab("Google")
        from PyQt6.QtCore import QUrl

        from iris.browser.search import BROWSER_HOME_URL

        view.load(QUrl(BROWSER_HOME_URL))
        return view

    def _hook_page(self, page) -> None:
        page.titleChanged.connect(lambda title, p=page: self._on_page_title(p, title))
        page.urlChanged.connect(lambda _url, p=page: self._on_page_url(p))

    def _tab_index_for(self, page) -> int:
        try:
            return self._pages.index(page)
        except ValueError:
            return -1

    def _on_page_title(self, page, title: str) -> None:
        idx = self._tab_index_for(page)
        if idx >= 0:
            self._tabs.setTabText(idx, (title or "New Tab")[:40])

    def _on_page_url(self, page) -> None:
        if self._view is None or page is not self._view.page():
            return
        try:
            self.apply_snapshot(self._session.snapshot())
        except Exception:
            pass

    def _on_new_tab(self) -> None:
        view = self.ensure_view()
        from iris.ui.browser.webengine_setup import new_browser_page

        page = new_browser_page(view, on_create_window=self._adopt_popup)
        self._hook_page(page)
        self._pages.append(page)
        self._tabs.addTab("Google")
        from PyQt6.QtCore import QUrl

        from iris.browser.search import BROWSER_HOME_URL

        page.load(QUrl(BROWSER_HOME_URL))
        self._tabs.setCurrentIndex(len(self._pages) - 1)

    def _on_tab_changed(self, index: int) -> None:
        if self._switching_tab or self._view is None:
            return
        if index < 0 or index >= len(self._pages):
            return
        page = self._pages[index]
        if self._view.page() is page:
            return
        self._switching_tab = True
        try:
            self._view.setPage(page)
            self.apply_snapshot(self._session.snapshot())
        finally:
            self._switching_tab = False

    def _on_tab_close(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        if len(self._pages) == 1:
            from iris.browser.types import Navigate

            from iris.browser.search import BROWSER_HOME_URL

            self._session.execute(Navigate(url=BROWSER_HOME_URL, source=Actor.HUMAN))
            self._tabs.setTabText(0, "Google")
            return
        page = self._pages.pop(index)
        self._switching_tab = True
        try:
            self._tabs.removeTab(index)
            nxt = min(index, len(self._pages) - 1)
            if self._view is not None:
                self._view.setPage(self._pages[nxt])
            self._tabs.setCurrentIndex(nxt)
        finally:
            self._switching_tab = False
        page.deleteLater()
        self.apply_snapshot(self._session.snapshot())

    def tab_count(self) -> int:
        return len(self._pages) if self._pages else self._tabs.count()

    def current_tab_index(self) -> int:
        idx = self._tabs.currentIndex()
        return idx if idx >= 0 else 0

    def _adopt_popup(self):
        """New window from the page. Do not setPage here — createWindow is still on the stack."""
        view = self.ensure_view()
        from iris.ui.browser.webengine_setup import new_browser_page

        page = new_browser_page(view, on_create_window=self._adopt_popup)
        self._hook_page(page)
        self._pages.append(page)
        self._tabs.addTab("New Tab")
        return page

    def view(self):
        return self._view

    def release_view(self):
        view = self._view
        if view is None:
            return None
        self._view_lay.removeWidget(view)
        return view

    def place_view(self, view) -> None:
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
        idx = self._tabs.currentIndex()
        if idx >= 0 and snap.title:
            self._tabs.setTabText(idx, snap.title[:40])

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
