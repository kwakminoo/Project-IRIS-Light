"""Composer 파일 첨부 칩 스트립 — 이미지·영상은 미리보기, 그 외는 이름."""

from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_ICON_PROVIDER = QFileIconProvider()
_ICON_PX = 16
_THUMB_PX = 88
_CHAT_MAX_W = 280
_CHAT_MAX_H = 200
_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
_VIDEO_EXT = frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".wmv"})


def at_ref_path(raw: str) -> str:
    """@참조에서 경로만. `C:` 드라이브 콜론은 자르지 않고 `:줄:칸`만 분리한다."""
    body = (raw or "").strip()
    if body.startswith("@"):
        body = body[1:].strip()
    from iris.ui.chat.chat_blocks import parse_file_chip_location

    path, _line, _col = parse_file_chip_location(body)
    return path or body


def format_byte_size(n: int) -> str:
    size = max(0, int(n))
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def chip_fs_path(path: str, *, workspace_root: str = "") -> Path | None:
    """칩이 가리키는 로컬 경로. 없으면 None."""
    raw = (path or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        rel = at_ref_path(raw)
        ws = (workspace_root or "").strip()
        candidate = Path(rel)
        if ws and not candidate.is_absolute():
            candidate = Path(ws).expanduser() / rel.replace("/", os.sep)
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            return None
        return candidate if candidate.suffix or candidate.name else None
    try:
        return Path(raw).expanduser()
    except OSError:
        return None


def composer_chip_kind(path: str, *, workspace_root: str = "") -> str:
    """확장자 대문자, 폴더, 또는 파일."""
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if fs is not None:
        try:
            if fs.is_dir():
                return "폴더"
        except OSError:
            pass
        suffix = fs.suffix
    else:
        suffix = Path(at_ref_path(path) if (path or "").startswith("@") else path).suffix
    ext = suffix.lower().lstrip(".")
    return ext.upper() if ext else "파일"


def composer_chip_meta(path: str, *, workspace_root: str = "") -> str:
    """칩 보조 줄 — 형식, 파일이면 크기."""
    kind = composer_chip_kind(path, workspace_root=workspace_root)
    if kind == "폴더":
        return kind
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if fs is None:
        return kind
    try:
        if fs.is_file():
            return f"{kind} · {format_byte_size(fs.stat().st_size)}"
    except OSError:
        pass
    return kind


def normalize_paths(paths: list[str]) -> list[str]:
    """파일 선택·드롭 공통. 존재하는 경로는 절대경로로, 파일명은 바꾸지 않는다."""
    out: list[str] = []
    for raw in paths:
        item = str(raw).strip().strip('"')
        if not item:
            continue
        if item.startswith("@"):
            token = item.split()[0]
            if token:
                out.append(token)
            continue
        try:
            path = Path(item).expanduser()
            if path.exists():
                path = path.resolve()
            out.append(str(path))
        except OSError:
            out.append(item)
    return out


def validate_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """normalize 후 실제 파일만 통과. 반환은 (ok, errors)."""
    return partition_attachment_paths(normalize_paths(paths))


def partition_attachment_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """파일 선택과 동일한 규칙 — 있는 로컬 경로와 @참조만 첨부.

    선택 대화상자는 존재하는 파일만 돌려준다. 용량·확장자 상한은 없다.
    """
    ok: list[str] = []
    errors: list[str] = []
    for raw in paths:
        item = str(raw).strip()
        if not item:
            continue
        if item.startswith("@"):
            token = item.split()[0]
            if token:
                ok.append(token)
            continue
        try:
            exists = Path(item).expanduser().exists()
        except OSError:
            exists = False
        if not exists:
            name = Path(item).name or item
            errors.append(f"파일을 찾을 수 없습니다: {name}")
            continue
        ok.append(item)
    return ok, errors


def attachment_filename(path: str) -> str:
    """칩·메시지에 쓰는 원본 파일명. 드라이브 콜론으로 자르지 않는다."""
    raw = (path or "").strip()
    if not raw:
        return ""
    target = at_ref_path(raw) if raw.startswith("@") else raw
    name = Path(target).name
    return name or target


def composer_chip_label(path: str) -> str:
    """칩 표시명 — @ref는 basename, 로컬 경로는 파일/폴더명."""
    return attachment_filename(path)


def _chip_icon_src(path: str, *, workspace_root: str = "") -> str:
    """OS 아이콘을 한 번만 저장. 채팅 HTML img src. 경로는 파일명에 넣지 않는다."""
    kind = composer_chip_kind(path, workspace_root=workspace_root)
    safe = "".join(ch if ch.isalnum() else "_" for ch in kind) or "file"
    dest = Path.home() / ".iris-light" / "chip-icons" / f"{safe}.png"
    try:
        if not dest.is_file():
            pix = composer_chip_icon(path, workspace_root=workspace_root)
            if pix.isNull():
                return ""
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not pix.save(str(dest), "PNG"):
                return ""
        return f"iris-chip:{safe}"
    except OSError:
        return ""


def media_kind(path: str, *, workspace_root: str = "") -> str:
    """있는 로컬 파일이 이미지면 image, 영상이면 video. 아니면 빈 문자열."""
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if fs is None:
        return ""
    try:
        if not fs.is_file():
            return ""
    except OSError:
        return ""
    suffix = fs.suffix.lower()
    if suffix in _IMAGE_EXT:
        return "image"
    if suffix in _VIDEO_EXT:
        return "video"
    return ""


def format_user_attachment_block(text: str, attachments: list[str]) -> str:
    """채팅에 올릴 사용자 문장. 이미지·영상은 전체 경로, 그 외는 파일명."""
    body = (text or "").strip()
    paths = [str(p).strip() for p in attachments if str(p).strip()]
    if not paths:
        return body
    media: list[str] = []
    files: list[str] = []
    for raw in paths:
        kind = media_kind(raw)
        shown = raw if kind else attachment_filename(raw)
        line = '@"' + shown.replace('"', "") + '"'
        (media if kind else files).append(line)
    parts: list[str] = []
    if body:
        parts.append(body)
    if media:
        parts.append("\n".join(media))
    if files:
        parts.append("[첨부 파일]\n" + "\n".join(files))
    return "\n\n".join(parts)


def _fit_image(img: QImage, max_w: int, max_h: int) -> QImage:
    if img.width() <= max_w and img.height() <= max_h:
        return img
    return img.scaled(
        max_w,
        max_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _stamp_play(img: QImage) -> QImage:
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(out.width(), out.height())
        diameter = max(28, side // 5)
        cx = out.width() // 2
        cy = out.height() // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 170))
        painter.drawEllipse(cx - diameter // 2, cy - diameter // 2, diameter, diameter)
        painter.setBrush(QColor(255, 255, 255))
        tri = QPainterPath()
        left = cx - diameter // 8
        top = cy - diameter // 5
        tri.moveTo(left, top)
        tri.lineTo(left, cy + diameter // 5)
        tri.lineTo(cx + diameter // 5, cy)
        tri.closeSubpath()
        painter.drawPath(tri)
    finally:
        painter.end()
    return out


def _blank_video_frame() -> QImage:
    img = QImage(320, 180, QImage.Format.Format_RGB32)
    img.fill(QColor(15, 23, 42))
    return img


def _shell_thumbnail(path: Path, side: int = 480) -> QImage | None:
    """탐색기 썸네일. 콘솔 프로그램(ffmpeg)을 띄우지 않는다."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_int), ("cy", ctypes.c_int)]

    class _BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", ctypes.c_long),
            ("bmWidth", ctypes.c_long),
            ("bmHeight", ctypes.c_long),
            ("bmWidthBytes", ctypes.c_long),
            ("bmPlanes", ctypes.c_ushort),
            ("bmBitsPixel", ctypes.c_ushort),
            ("bmBits", ctypes.c_void_p),
        ]

    class _HEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    gdi32 = ctypes.WinDLL("gdi32")
    ole32.CoInitialize(None)
    iid = _GUID()
    if ole32.CLSIDFromString(
        ctypes.c_wchar_p("{bcc18b79-ba16-442f-80c4-8a59c30c463b}"), ctypes.byref(iid)
    ):
        return None
    factory = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(
        ctypes.c_wchar_p(str(path)), None, ctypes.byref(iid), ctypes.byref(factory)
    ):
        return None
    if not factory.value:
        return None
    funcs = ctypes.cast(
        ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_image = ctypes.WINFUNCTYPE(
        ctypes.HRESULT, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
    )(funcs[3])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(funcs[2])
    bitmap = ctypes.c_void_p()
    try:
        # THUMBNAILONLY | BIGGERSIZEOK — 아이콘이 아니라 그림·첫 장면
        if get_image(factory, _SIZE(side, side), 0x8 | 0x1, ctypes.byref(bitmap)) or not bitmap.value:
            return None
        info = _BITMAP()
        gdi32.GetObjectW(bitmap, ctypes.sizeof(info), ctypes.byref(info))
        width, height = int(info.bmWidth), abs(int(info.bmHeight))
        if width <= 0 or height <= 0:
            return None
        header = _HEADER()
        header.biSize = ctypes.sizeof(_HEADER)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        buf = ctypes.create_string_buffer(width * height * 4)
        hdc = gdi32.CreateCompatibleDC(None)
        try:
            if gdi32.GetDIBits(hdc, bitmap, 0, height, buf, ctypes.byref(header), 0) <= 0:
                return None
        finally:
            gdi32.DeleteDC(hdc)
        image = QImage(buf, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied)
        copied = image.copy()
        return None if copied.isNull() else copied
    finally:
        if bitmap.value:
            gdi32.DeleteObject(bitmap)
        release(factory)


def _video_frame(path: Path) -> QImage | None:
    return _shell_thumbnail(path)


def load_media_frame(path: str, *, workspace_root: str = "") -> QImage | None:
    kind = media_kind(path, workspace_root=workspace_root)
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if not kind or fs is None:
        return None
    if kind == "image":
        image = QImage(str(fs))
        return None if image.isNull() else image
    return _video_frame(fs)


def chat_media_thumb(path: str, *, workspace_root: str = "") -> str:
    """채팅에 넣을 미리보기 PNG. 원본이 바뀌면 다시 만든다."""
    kind = media_kind(path, workspace_root=workspace_root)
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if not kind or fs is None:
        return ""
    try:
        st = fs.stat()
        digest = hashlib.sha1(
            f"{fs}|{st.st_mtime_ns}|{st.st_size}|{kind}".encode()
        ).hexdigest()[:16]
    except OSError:
        return ""
    dest = Path.home() / ".iris-light" / "media-thumbs" / f"{digest}.png"
    if dest.is_file():
        return str(dest)
    frame = load_media_frame(path, workspace_root=workspace_root)
    if frame is None:
        if kind != "video":
            return ""
        frame = _blank_video_frame()
    if kind == "video":
        frame = _stamp_play(frame)
    frame = _fit_image(frame, _CHAT_MAX_W, _CHAT_MAX_H)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not frame.save(str(dest), "PNG"):
            return ""
    except OSError:
        return ""
    return str(dest)


def _rounded_cover(src: QPixmap, side: int, radius: int) -> QPixmap:
    scaled = src.scaled(
        side,
        side,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - side) // 2)
    y = max(0, (scaled.height() - side) // 2)
    cropped = scaled.copy(x, y, side, side)
    out = QPixmap(side, side)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, side, side, radius, radius)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, cropped)
    finally:
        painter.end()
    return out


def composer_media_pixmap(path: str, *, workspace_root: str = "", side: int = _THUMB_PX) -> QPixmap:
    kind = media_kind(path, workspace_root=workspace_root)
    if not kind:
        return QPixmap()
    frame = load_media_frame(path, workspace_root=workspace_root)
    if frame is None:
        if kind != "video":
            return QPixmap()
        frame = _blank_video_frame()
    if kind == "video":
        frame = _stamp_play(frame)
    return _rounded_cover(QPixmap.fromImage(frame), side, 12)


def media_preview_html(path: str, *, workspace_root: str = "") -> str:
    """채팅 말풍선용 미리보기. 이미지는 클릭 시 크게, 영상은 기본 앱으로."""
    kind = media_kind(path, workspace_root=workspace_root)
    thumb = chat_media_thumb(path, workspace_root=workspace_root)
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if not kind or not thumb or fs is None:
        return ""
    image = QImage(thumb)
    if image.isNull():
        return ""
    target = str(fs.resolve())
    if kind == "video":
        href = "iris-video:" + quote(target, safe="")
    else:
        from iris.core.markdown_text import iris_image_href

        href = iris_image_href(target)
    src = html.escape(thumb.replace("\\", "/"), quote=True)
    return (
        f'<a href="{html.escape(href, quote=True)}" style="text-decoration:none;">'
        f'<img src="{src}" width="{image.width()}" height="{image.height()}" /></a>'
    )


def attachment_chip_html(path: str, *, workspace_root: str = "") -> str:
    """파일 선택·드롭·전송 메시지 공통. 이미지·영상은 미리보기, 나머지는 이름."""
    preview = media_preview_html(path, workspace_root=workspace_root)
    if preview:
        return preview
    name = html.escape(composer_chip_label(path))
    meta = html.escape(composer_chip_meta(path, workspace_root=workspace_root))
    src = _chip_icon_src(path, workspace_root=workspace_root)
    icon = (
        f'<img src="{html.escape(src, quote=True)}" width="16" height="16" /> '
        if src
        else ""
    )
    return (
        '<span style="background-color:rgba(56,189,248,0.12);'
        'border:1px solid rgba(56,189,248,0.28);border-radius:10px;">'
        f"{icon}{name}"
        f' <span style="color:#94a3b8;font-size:10px;">{meta}</span></span>'
    )


def composer_chip_icon(path: str, *, workspace_root: str = "") -> QPixmap:
    """칩 아이콘 — OS 파일 아이콘(QFileIconProvider)."""
    raw = (path or "").strip()
    fs_path = raw
    if raw.startswith("@"):
        rel = at_ref_path(raw)
        ws = (workspace_root or "").strip()
        if ws:
            candidate = Path(ws).expanduser() / rel.replace("/", os.sep)
            if candidate.exists():
                fs_path = str(candidate.resolve())
            else:
                ext = Path(rel).suffix
                if not ext:
                    icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.Folder)
                else:
                    icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.File)
                return icon.pixmap(_ICON_PX, _ICON_PX)
    p = Path(fs_path)
    if p.is_dir():
        icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.Folder)
    elif p.is_file():
        icon = _ICON_PROVIDER.icon(QFileInfo(str(p.resolve())))
    else:
        icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.File)
    return icon.pixmap(_ICON_PX, _ICON_PX)


class ComposerAttachmentStrip(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerAttachmentStrip")
        self._paths: list[str] = []
        self._workspace_root = ""
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 0, 8, 4)
        self._row.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hide()

    def set_workspace_root(self, root: str) -> None:
        self._workspace_root = (root or "").strip()
        if self._paths:
            self._rebuild()

    def paths(self) -> list[str]:
        return list(self._paths)

    def add_paths(self, paths: list[str]) -> None:
        for raw in paths:
            p = str(raw).strip()
            if not p:
                continue
            token = p.split()[0] if p.startswith("@") else p
            if token in self._paths:
                continue
            self._paths.append(token)
        self._rebuild()

    def take_paths(self) -> list[str]:
        out = list(self._paths)
        self._paths.clear()
        self._rebuild()
        return out

    def clear_paths(self) -> None:
        self._paths.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._paths:
            self.hide()
            self.changed.emit()
            return
        for path in self._paths:
            self._row.addWidget(self._make_chip(path))
        self._row.addStretch(1)
        self.show()
        self.changed.emit()

    def _make_chip(self, path: str) -> QWidget:
        pix = composer_media_pixmap(path, workspace_root=self._workspace_root)
        if not pix.isNull():
            return self._make_media_chip(path, pix)
        wrap = QWidget()
        wrap.setObjectName("ComposerAttachmentChip")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(6, 2, 4, 2)
        lay.setSpacing(4)

        icon_label = QLabel()
        icon_label.setFixedSize(_ICON_PX, _ICON_PX)
        icon_label.setPixmap(
            composer_chip_icon(path, workspace_root=self._workspace_root)
        )
        icon_label.setScaledContents(True)

        name = composer_chip_label(path)
        meta_text = composer_chip_meta(path, workspace_root=self._workspace_root)
        label = QLabel(name)
        label.setToolTip(f"{name} · {meta_text}")
        label.setStyleSheet("color: #e2e8f0; font-size: 11px; background: transparent; border: none;")

        meta = QLabel(meta_text)
        meta.setObjectName("ComposerAttachmentMeta")
        meta.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent; border: none;")

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        text_col.addWidget(label)
        text_col.addWidget(meta)

        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setFlat(True)
        btn.setToolTip("첨부 취소")
        btn.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        btn.clicked.connect(lambda _=False, p=path: self._remove(p))

        lay.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(text_col)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        wrap.setStyleSheet(
            """
            QWidget#ComposerAttachmentChip {
                background: rgba(56, 189, 248, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 10px;
            }
            """
        )
        return wrap

    def _make_media_chip(self, path: str, pix: QPixmap) -> QWidget:
        side = pix.width()
        wrap = QWidget()
        wrap.setObjectName("ComposerAttachmentChip")
        wrap.setFixedSize(side, side)
        wrap.setStyleSheet(
            "QWidget#ComposerAttachmentChip { background: transparent; border: none; }"
        )
        image = QLabel(wrap)
        image.setPixmap(pix)
        image.setFixedSize(side, side)
        image.move(0, 0)
        image.setToolTip(composer_chip_label(path))
        btn = QPushButton("×", wrap)
        btn.setFixedSize(18, 18)
        btn.move(side - 20, 2)
        btn.setFlat(True)
        btn.setToolTip("첨부 취소")
        btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(15, 23, 42, 0.72);"
            " border: none; border-radius: 9px; font-size: 12px; }"
        )
        btn.clicked.connect(lambda _=False, p=path: self._remove(p))
        return wrap

    def _remove(self, path: str) -> None:
        self._paths = [p for p in self._paths if p != path]
        self._rebuild()
