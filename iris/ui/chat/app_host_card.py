"""채팅 칸 안의 MCP Apps 호스트 카드 (Phase 1).

로그(QTextEdit) 안에 웹뷰를 넣지 않는다. DiagramCard와 같이 로그·입력창 사이 슬롯.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ui.chat.app_host_bridge import (
    METHOD_PING,
    AppHostMessage,
    AppHostOffer,
    AppHostPhase,
    parse_message,
    pong_for,
    serialize_message,
)
from iris.ui.shared.theme_tokens import TOKENS

# Host → page: invoke the fixture's onHostMessage.
_DELIVER_JS = """
(function(raw) {
  try {
    var msg = (typeof raw === 'string') ? JSON.parse(raw) : raw;
    if (typeof window.__irisOnHostMessage === 'function') {
      window.__irisOnHostMessage(msg);
      return true;
    }
  } catch (e) {}
  return false;
})
"""


class _PageHostBridge(QObject):
    """Qt WebChannel object exposed as `irisHost` inside the page."""

    message_from_page = pyqtSignal(str)

    @pyqtSlot(str)
    def postMessage(self, raw: str) -> None:
        self.message_from_page.emit(str(raw or ""))


class AppHostCard(QFrame):
    """로그와 입력창 사이의 앱 호스트 카드. 웹뷰는 첫 표시 때 하나."""

    phase_changed = pyqtSignal(str)
    handshake_ok = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("AppHostCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QFrame#AppHostCard {"
            f"background:{TOKENS.space_navy};"
            f"border:1px solid {TOKENS.text_muted};"
            "border-radius:8px;"
            "}"
            "QPushButton#AppHostCardClose {"
            f"color:{TOKENS.text_secondary};"
            "background:transparent;"
            f"border:1px solid {TOKENS.text_muted};"
            "border-radius:4px;"
            "padding:0 8px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel("앱", self)
        self._title.setStyleSheet(
            f"color:{TOKENS.text_secondary}; background:transparent; border:0;"
        )
        close = QPushButton("닫기", self)
        close.setObjectName("AppHostCardClose")
        close.setFixedHeight(22)
        close.clicked.connect(self.close_host)
        head.addWidget(self._title, 1)
        head.addWidget(close, 0)
        layout.addLayout(head)
        self._view_slot = QWidget(self)
        self._view_slot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._view_slot, 1)
        self._view = None
        self._channel = None
        self._bridge = _PageHostBridge(self)
        self._bridge.message_from_page.connect(self._on_page_raw)
        self._phase = AppHostPhase.IDLE
        self._last_ping: AppHostMessage | None = None
        self._pong_delivered = False
        self.hide()

    @property
    def phase(self) -> AppHostPhase:
        return self._phase

    @property
    def handshake_complete(self) -> bool:
        return self._phase is AppHostPhase.READY and self._pong_delivered

    def show_offer(self, offer: AppHostOffer) -> bool:
        path = Path(offer.html_path)
        if not path.is_file():
            return False
        label = (offer.title or path.stem or "앱").strip() or "앱"
        self._title.setText(label)
        self._pong_delivered = False
        self._last_ping = None
        self._set_phase(AppHostPhase.LOADING)
        view = self._ensure_view()
        view.load(QUrl.fromLocalFile(str(path.resolve())))
        self.show()
        return True

    def close_host(self) -> None:
        self._set_phase(AppHostPhase.CLOSED)
        self.hide()

    def post_to_page(self, msg: AppHostMessage) -> None:
        if self._view is None:
            return
        raw = serialize_message(msg)
        self._view.page().runJavaScript(f"{_DELIVER_JS}({json_quote(raw)})")

    def _set_phase(self, phase: AppHostPhase) -> None:
        if self._phase is phase:
            return
        self._phase = phase
        self.phase_changed.emit(phase.value)

    def _ensure_view(self):
        if self._view is not None:
            return self._view
        # WebEngine import must follow ensure_qt_webengine_ready + QApplication.
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(self)
        # ponytail: Apps are local documents; grant network/file expansion only with a permission UI.
        settings = view.settings()
        for attr in (
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
        ):
            settings.setAttribute(attr, False)
        channel = QWebChannel(view.page())
        channel.registerObject("irisHost", self._bridge)
        view.page().setWebChannel(channel)
        view.loadFinished.connect(self._on_load_finished)
        layout = self.layout()
        layout.replaceWidget(self._view_slot, view)
        self._view_slot.hide()
        self._view_slot.deleteLater()
        self._view_slot = None
        self._view = view
        self._channel = channel
        return view

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self._set_phase(AppHostPhase.IDLE)

    def _on_page_raw(self, raw: str) -> None:
        msg = parse_message(raw)
        if msg is None:
            return
        if msg.method != METHOD_PING:
            return
        self._last_ping = msg
        pong = pong_for(msg)
        self.post_to_page(pong)
        self._pong_delivered = True
        self._set_phase(AppHostPhase.READY)
        self.handshake_ok.emit()


def json_quote(raw: str) -> str:
    """JSON string literal for embedding inside runJavaScript."""
    return json.dumps(raw, ensure_ascii=False)


def fixture_ping_html() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "app_host_ping.html"
