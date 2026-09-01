"""채팅 인라인 이미지 — 원격 로드 + 클릭 확대(라이트박스)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PyQt6.QtCore import QObject, Qt, QThreadPool, QRunnable, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QImage, QKeyEvent, QPixmap, QTextDocument
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.core.markdown_text import extract_chat_image_srcs, parse_iris_image_href
from iris.ui.chat.chat_blocks import parse_copy_anchor, parse_file_chip_location, parse_iris_file_anchor

_MAX_BYTES = 8 * 1024 * 1024
_UA = "IrisLight/1.0 (chat-image)"


class _FetchSignals(QObject):
    done = pyqtSignal(str, object)  # src, QImage | None


class _FetchJob(QRunnable):
    def __init__(self, src: str, signals: _FetchSignals) -> None:
        super().__init__()
        self._src = src
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802
        img = _load_image_sync(self._src)
        self._signals.done.emit(self._src, img)


def _load_image_sync(src: str) -> QImage | None:
    raw = (src or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("data:"):
            # data:image/png;base64,...
            from PyQt6.QtCore import QByteArray

            qimg = QImage.fromData(QByteArray.fromPercentEncoding(raw.encode("utf-8")))
            # QImage.fromData doesn't parse data URIs — decode manually
            if "base64," in raw:
                import base64

                b64 = raw.split("base64,", 1)[1]
                qimg = QImage.fromData(base64.b64decode(b64))
                return None if qimg.isNull() else qimg
            return None
        if raw.startswith("file:"):
            path = QUrl(raw).toLocalFile()
            qimg = QImage(path)
            return None if qimg.isNull() else qimg
        # 로컬 경로
        p = Path(raw)
        if p.is_file():
            qimg = QImage(str(p))
            return None if qimg.isNull() else qimg
        if raw.startswith("http://") or raw.startswith("https://"):
            req = Request(raw, headers={"User-Agent": _UA, "Accept": "image/*,*/*"})
            with urlopen(req, timeout=12) as resp:
                data = resp.read(_MAX_BYTES + 1)
            if len(data) > _MAX_BYTES:
                return None
            qimg = QImage.fromData(data)
            return None if qimg.isNull() else qimg
    except Exception:
        return None
    return None


class ChatImageLoader(QObject):
    """QTextEdit 문서에 원격/로컬 이미지를 addResource로 주입."""

    def __init__(self, document: QTextDocument, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._doc = document
        self._cache: dict[str, QImage] = {}
        self._inflight: set[str] = set()
        self._pool = QThreadPool.globalInstance()
        self._signals = _FetchSignals()
        self._signals.done.connect(self._on_fetched)

    def prefetch_from_html(self, html_body: str) -> None:
        for src in extract_chat_image_srcs(html_body):
            self.ensure(src)

    def ensure(self, src: str) -> None:
        key = (src or "").strip()
        if not key or key in self._cache or key in self._inflight:
            return
        # 로컬은 동기 로드 (빠름)
        if not key.startswith("http://") and not key.startswith("https://"):
            img = _load_image_sync(key)
            if img is not None:
                self._install(key, img)
            return
        self._inflight.add(key)
        self._pool.start(_FetchJob(key, self._signals))

    def _on_fetched(self, src: str, img: object) -> None:
        self._inflight.discard(src)
        if isinstance(img, QImage) and not img.isNull():
            self._install(src, img)

    def _install(self, src: str, img: QImage) -> None:
        self._cache[src] = img
        self._doc.addResource(
            int(QTextDocument.ResourceType.ImageResource),
            QUrl(src),
            img,
        )
        # 이미 삽입된 img 갱신
        n = self._doc.characterCount()
        if n > 0:
            self._doc.markContentsDirty(0, n)


def show_image_lightbox(parent: QWidget | None, src: str) -> None:
    """이미지/GIF를 크게 보는 모달. Esc·클릭으로 닫기."""
    raw = (src or "").strip()
    if not raw:
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle("이미지")
    dlg.setModal(True)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setStyleSheet(
        "QDialog { background-color: rgba(2, 6, 23, 0.96); }"
        "QLabel { background: transparent; color: #94a3b8; }"
        "QScrollArea { background: transparent; border: none; }"
    )

    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
    label.setCursor(Qt.CursorShape.PointingHandCursor)
    label.setToolTip("클릭하거나 Esc로 닫기")
    scroll.setWidget(label)
    root.addWidget(scroll)

    screen = dlg.screen() or (parent.screen() if parent else None)
    max_w = 960
    max_h = 720
    if screen is not None:
        geo = screen.availableGeometry()
        max_w = max(320, int(geo.width() * 0.85))
        max_h = max(240, int(geo.height() * 0.85))

    movie = None
    lower = raw.lower()
    is_gif = lower.endswith(".gif") or ".gif?" in lower
    if is_gif and (raw.startswith("http://") or raw.startswith("https://") or Path(raw).is_file()):
        try:
            from PyQt6.QtGui import QMovie

            if raw.startswith("http://") or raw.startswith("https://"):
                # ponytail: GIF는 임시 파일에 받아 QMovie로 재생. 천장=디스크 캐시 없음.
                import tempfile

                req = Request(raw, headers={"User-Agent": _UA, "Accept": "image/*,*/*"})
                with urlopen(req, timeout=12) as resp:
                    data = resp.read(_MAX_BYTES + 1)
                if len(data) <= _MAX_BYTES:
                    tmp = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
                    tmp.write(data)
                    tmp.close()
                    movie = QMovie(tmp.name)
            else:
                movie = QMovie(raw)
            if movie is not None and movie.isValid():
                label.setMovie(movie)
                movie.start()
        except Exception:
            movie = None

    if movie is None:
        img = _load_image_sync(raw)
        if img is None or img.isNull():
            label.setText("이미지를 불러올 수 없습니다.")
        else:
            pm = QPixmap.fromImage(img)
            if pm.width() > max_w or pm.height() > max_h:
                pm = pm.scaled(
                    max_w,
                    max_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            label.setPixmap(pm)

    def _close(_ev: object | None = None) -> None:
        dlg.accept()

    label.mousePressEvent = lambda ev: _close(ev)  # type: ignore[method-assign]

    def _key(ev: QKeyEvent) -> None:
        if ev.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            dlg.accept()
            return
        QDialog.keyPressEvent(dlg, ev)

    dlg.keyPressEvent = _key  # type: ignore[method-assign]
    dlg.resize(min(max_w + 40, 1000), min(max_h + 40, 760))
    dlg.exec()


def _find_main_window(widget: QWidget | None):
    w = widget
    while w is not None:
        if hasattr(w, "_get_bound_ide_session"):
            return w
        w = w.parentWidget()
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            for top in app.topLevelWidgets():
                if hasattr(top, "_get_bound_ide_session"):
                    return top
    except Exception:
        return None
    return None


def _resolve_file_chip_abs_path(window, rel_path: str) -> str | None:
    path_part, _, _ = parse_file_chip_location(rel_path)
    if not path_part:
        return None
    candidate = Path(path_part)
    if candidate.is_file():
        return str(candidate.resolve())
    session = window._get_bound_ide_session(refresh=False)
    if session and session.workspace_root:
        under_ws = (Path(session.workspace_root) / path_part).resolve()
        if under_ws.is_file():
            return str(under_ws)
    try:
        from iris.storage.user_profile import load_user_profile

        profile = load_user_profile(window._db)
        root = (profile.project_root or "").strip()
        if root:
            under_root = (Path(root) / path_part).resolve()
            if under_root.is_file():
                return str(under_root)
    except Exception:
        return None
    return None


def _open_file_chip_in_ide(parent: QWidget, rel_path: str) -> bool:
    window = _find_main_window(parent)
    if window is None:
        return False
    session = window._get_bound_ide_session(refresh=True)
    if session is None or getattr(window, "_ui_mode", "") != "ide_companion":
        return False
    abs_path = _resolve_file_chip_abs_path(window, rel_path)
    if not abs_path:
        return False
    _, line, column = parse_file_chip_location(rel_path)
    from iris.ui.control_bindings import _ide_open_file_path

    result = _ide_open_file_path(window, abs_path, line=line, column=column)
    return bool(result.get("ok"))


def handle_chat_anchor_click(parent: QWidget, anchor: str) -> bool:
    """iris-copy / iris-image / iris-file / http(s) 앵커 처리. True면 이벤트 소비."""
    code = parse_copy_anchor(anchor)
    if code is not None:
        QGuiApplication.clipboard().setText(code)
        return True
    rel_path = parse_iris_file_anchor(anchor)
    if rel_path is not None:
        _open_file_chip_in_ide(parent, rel_path)
        return True
    img_src = parse_iris_image_href(anchor)
    if img_src:
        show_image_lightbox(parent, img_src)
        return True
    if anchor.startswith("http://") or anchor.startswith("https://"):
        # 직접 이미지 URL이면 라이트박스, 아니면 브라우저
        path = urlparse(anchor).path.lower()
        if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")):
            show_image_lightbox(parent, anchor)
            return True
        QDesktopServices.openUrl(QUrl(anchor))
        return True
    return False


def attach_image_loader(text_edit: QWidget) -> ChatImageLoader:
    """QTextEdit에 로더를 붙이고 document에 연결."""
    doc = text_edit.document()  # type: ignore[attr-defined]
    loader = ChatImageLoader(doc, text_edit)
    text_edit._iris_image_loader = loader  # type: ignore[attr-defined]
    return loader


def prefetch_chat_html_images(text_edit: QWidget, html_body: str) -> None:
    loader = getattr(text_edit, "_iris_image_loader", None)
    if loader is None:
        loader = attach_image_loader(text_edit)
    loader.prefetch_from_html(html_body)


if __name__ == "__main__":
    from iris.ui.chat.chat_blocks import file_anchor_for, parse_iris_file_anchor

    rel = "iris/ui/chat/chat_blocks.py:12:3"
    assert parse_iris_file_anchor(file_anchor_for(rel)) == rel
    assert parse_iris_file_anchor("iris-copy://x") is None
    print("chat_image_view file anchor ok")
