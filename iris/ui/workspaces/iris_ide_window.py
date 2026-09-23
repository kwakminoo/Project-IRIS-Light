"""IRIS IDE — PyQt6 QWebEngine window for embedded Theia."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

from iris.assets.branding import load_app_icon
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.window.frameless_chrome import suppress_native_window_border

IRIS_IDE_TITLE = "IRIS IDE"


def _iris_ide_window_stylesheet() -> str:
    t = TOKENS
    return f"""
    QMainWindow {{
        background: {t.void_black};
        border: none;
    }}
    QWidget#IrisIdeLoading {{
        background: {t.void_black};
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
    """Separate top-level window — welcome / Theia in QWebEngineView."""

    theia_load_finished = pyqtSignal(bool)
    files_dropped = pyqtSignal(list)
    folder_opened = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(IRIS_IDE_TITLE)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(640, 480)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(_iris_ide_window_stylesheet())
        self.setAcceptDrops(True)
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
        self._loading_label.setWordWrap(True)
        load_lay.addWidget(title)
        load_lay.addWidget(self._loading_label)
        self._stack.addWidget(self._loading)

        self._welcome = IrisIdeWelcomeLayer()
        self._welcome.folder_opened.connect(self.folder_opened.emit)
        self._stack.addWidget(self._welcome)

        self._view: QWebEngineView | None = None
        self._loaded_url = ""
        self._loaded_workspace = ""
        self._defer_show = False
        self._load_hooked = False
        # ponytail: "embedded" = Companion에 도킹된 자식 HWND (QWidget 임베드 아님)
        self._embedded = False

    def set_embedded(self, embedded: bool, *, host: QWidget | None = None) -> None:
        """Companion 도킹 — 항상 top-level HWND 유지 (Qt.Widget 임베드 금지).

        WA_Translucent 조상 트리 아래 QMainWindow→Widget 재부모는
        QWebEngine(터미널·단축키·포커스) 입력을 깨뜨린다. 시각적 단일 창은
        호스트 rect에 geometry만 맞춘 자식 Window로 구현한다.
        """
        embedded = bool(embedded)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if embedded:
            self._embedded = True
            self.setMinimumSize(0, 0)
            # setParent(host, flags) — 플래그+부모 원자적 (setWindowFlags만 쓰면 부모 유실)
            self.setParent(host, flags)
        else:
            was = self._embedded
            self._embedded = False
            self.setParent(None, flags)
            self.setMinimumSize(640, 480)
            if was:
                self._frameless_chrome_applied = False

    def is_embedded(self) -> bool:
        return self._embedded

    def apply_frameless_chrome(self) -> None:
        """Companion/타일 — Win11 DWM 1px 테두리 숨김 (FramelessWindowHint는 __init__)."""
        suppress_native_window_border(self)
        self._frameless_chrome_applied = True

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._frameless_chrome_applied:
            self.apply_frameless_chrome()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        from iris.ui.window.file_drop import mime_has_attachable

        if mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        from iris.ui.window.file_drop import mime_has_attachable

        if mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        from iris.ui.window.file_drop import paths_from_mime

        paths = paths_from_mime(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _ensure_view(self) -> QWebEngineView | None:
        if self._view is not None:
            return self._view
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView
        except ImportError:  # pragma: no cover
            return None

        # ponytail: WebEngine AcceptDrops=True면 Chromium이 OS 파일 드롭을 가로챔
        self._view = _QWebEngineView()
        self._view.setAcceptDrops(False)
        self._view.setStyleSheet(f"background: {TOKENS.void_black};")
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

    def show_welcome(self, *, show_window: bool = True) -> None:
        """Companion 진입 기본화면 — 저장된 폴더를 자동으로 열지 않음."""
        self._welcome.refresh_recent_folders()
        self._stack.setCurrentWidget(self._welcome)
        if show_window:
            self.show()
            self.raise_()

    def show_loading(self, message: str = "IRIS IDE 시작 중…", *, show_window: bool = True) -> None:
        self._loading_label.setText(message)
        self._stack.setCurrentWidget(self._loading)
        if show_window:
            self.show()
            self.raise_()

    def load_theia(
        self,
        url: str,
        *,
        bridge_port: int = 0,
        bridge_token: str = "",
        control_port: int = 0,
        control_token: str = "",
        workspace: str = "",
        force_reload: bool = False,
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
        if control_port and control_token:
            sep = "&" if "?" in url else "?"
            url = (
                f"{url}{sep}iris_control_port={int(control_port)}"
                f"&iris_control_token={quote(control_token, safe='')}"
            )
        ws = (workspace or "").strip()
        if ws:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}iris_ws={quote(ws, safe='')}"
        if force_reload or (ws and ws != self._loaded_workspace):
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}iris_reload={int(time.time() * 1000)}"
        if on_ready is not None:
            self.theia_load_finished.connect(on_ready, type=Qt.ConnectionType.SingleShotConnection)
        self._defer_show = defer_show
        same_url = url == self._loaded_url and not force_reload
        if same_url and self._stack.currentWidget() is view:
            if defer_show:
                self.theia_load_finished.emit(True)
            else:
                self.show()
                self.raise_()
            return
        self._loaded_url = url
        self._loaded_workspace = ws
        view.load(QUrl(url))
        self._stack.setCurrentWidget(view)
        if defer_show:
            return
        self.show()
        self.raise_()
        self.focus_theia_view()

    def hide_window(self) -> None:
        self.hide()

    def close_window(self) -> None:
        """Companion/앱 종료 시 IDE 창을 완전히 닫는다 (hide만 하면 유령 창이 남음)."""
        self._loaded_url = ""
        self._loaded_workspace = ""
        self._defer_show = False
        if self._embedded:
            self.set_embedded(False)
        self.hide()
        self.close()

    def focus_theia_view(self) -> None:
        """터미널/단축키용 — WebEngine에 포커스 한 번."""
        if self._view is None:
            return
        if self._stack.currentWidget() is not self._view:
            return
        self.raise_()
        self.activateWindow()
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def is_welcome_visible(self) -> bool:
        return self._stack.currentWidget() is self._welcome

    def is_opening(self) -> bool:
        """Theia 기동/로드 대기 — Opening… 화면."""
        return self._stack.currentWidget() is self._loading

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
    w.show_welcome()
    assert w.is_welcome_visible()
    assert w.windowTitle() == IRIS_IDE_TITLE
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "iris_icon.png"
    assert icon_path.is_file()
    assert TOKENS.void_black in w.styleSheet()
    print("iris_ide_window ok")


if __name__ == "__main__":
    _self_check()
