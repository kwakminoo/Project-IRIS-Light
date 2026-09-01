"""IRIS IDE — PyQt6 QWebEngine window for embedded Theia."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

from iris.assets.branding import load_app_icon
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.window.frameless_chrome import suppress_native_window_border

IRIS_IDE_TITLE = "IRIS IDE"


def _iris_ide_window_stylesheet() -> str:
    t = TOKENS
    return f"""
    QMainWindow {{
        background: {t.background_primary};
        border: none;
    }}
    QWidget#IrisIdeLoading {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.space_navy},
            stop:0.45 {t.background_primary},
            stop:1 {t.void_black}
        );
        border: none;
        border-radius: 0;
    }}
    QLabel#IrisIdeLoadingTitle {{
        color: {t.text_accent};
        font-size: 20px;
        font-weight: 600;
        font-family: {t.font_family};
        letter-spacing: 0.04em;
    }}
    QLabel#IrisIdeLoadingHint {{
        color: {t.text_secondary};
        font-size: 14px;
        font-family: {t.font_family};
    }}
    """


class IrisIdeWindow(QMainWindow):
    """Separate top-level window — Theia in QWebEngineView."""

    theia_load_finished = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(IRIS_IDE_TITLE)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(640, 480)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(_iris_ide_window_stylesheet())
        self._frameless_chrome_applied = False
        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._loading = QWidget()
        self._loading.setObjectName("IrisIdeLoading")
        load_lay = QVBoxLayout(self._loading)
        load_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        load_lay.setSpacing(TOKENS.spacing_md)
        title = QLabel("IRIS IDE")
        title.setObjectName("IrisIdeLoadingTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel("IRIS IDE 시작 중…")
        self._loading_label.setObjectName("IrisIdeLoadingHint")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        load_lay.addWidget(title)
        load_lay.addWidget(self._loading_label)
        self._stack.addWidget(self._loading)

        self._view: QWebEngineView | None = None
        self._loaded_url = ""
        self._defer_show = False
        self._load_hooked = False

    def apply_frameless_chrome(self) -> None:
        """Companion/타일 — Win11 DWM 1px 테두리 숨김 (FramelessWindowHint는 __init__)."""
        suppress_native_window_border(self)
        self._frameless_chrome_applied = True

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._frameless_chrome_applied:
            self.apply_frameless_chrome()

    def _ensure_view(self) -> QWebEngineView | None:
        if self._view is not None:
            return self._view
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView
        except ImportError:  # pragma: no cover
            return None
        self._view = _QWebEngineView()
        self._view.setStyleSheet(f"background: {TOKENS.background_primary};")
        if not self._load_hooked:
            self._view.loadFinished.connect(self._on_theia_load_finished)
            self._load_hooked = True
        self._stack.addWidget(self._view)
        return self._view

    def _on_theia_load_finished(self, ok: bool) -> None:
        self.theia_load_finished.emit(ok)
        if ok and self._defer_show:
            self._defer_show = False
            self.show()
            self.raise_()

    def show_loading(self, message: str = "IRIS IDE 시작 중…", *, show_window: bool = True) -> None:
        self._loading_label.setText(message)
        self._stack.setCurrentWidget(self._loading)
        if show_window:
            self.show()

    def load_theia(
        self,
        url: str,
        *,
        bridge_port: int = 0,
        bridge_token: str = "",
        defer_show: bool = False,
        on_ready: Callable[[bool], None] | None = None,
    ) -> None:
        url = (url or "").strip()
        view = self._ensure_view()
        if not url or view is None:
            self.show_loading("Theia URL 없음 — IRIS IDE 설치/복구 필요")
            return
        if bridge_port and bridge_token:
            sep = "&" if "?" in url else "?"
            url = (
                f"{url}{sep}iris_bridge_port={int(bridge_port)}"
                f"&iris_bridge_token={bridge_token}"
            )
        if on_ready is not None:
            self.theia_load_finished.connect(on_ready, type=Qt.ConnectionType.SingleShotConnection)
        self._defer_show = defer_show
        if url == self._loaded_url and self._stack.currentWidget() is view:
            if defer_show:
                self.theia_load_finished.emit(True)
            else:
                self.show()
                self.raise_()
            return
        self._loaded_url = url
        view.load(QUrl(url))
        self._stack.setCurrentWidget(view)
        if defer_show:
            return
        self.show()
        self.raise_()

    def hide_window(self) -> None:
        self.hide()

    def close_window(self) -> None:
        """Companion/앱 종료 시 IDE 창을 완전히 닫는다 (hide만 하면 유령 창이 남음)."""
        self._loaded_url = ""
        self._defer_show = False
        self.hide()
        self.close()

    def is_theia_loaded(self) -> bool:
        return bool(self._loaded_url) and self._view is not None and self._stack.currentWidget() is self._view


def iris_ide_icon(size: int = 40) -> QIcon:
    return load_app_icon()


def _self_check() -> None:
    from PyQt6.QtWidgets import QApplication
    import sys

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication(sys.argv)
    w = IrisIdeWindow()
    assert w.windowFlags() & Qt.WindowType.FramelessWindowHint
    w.show_loading()
    assert w.windowTitle() == IRIS_IDE_TITLE
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "iris_icon.png"
    assert icon_path.is_file()
    assert TOKENS.background_primary in w.styleSheet()
    print("iris_ide_window ok")


if __name__ == "__main__":
    _self_check()
