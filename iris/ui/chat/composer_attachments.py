"""Composer 파일 첨부 칩 스트립 — Cursor식 이름 + 아이콘."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

_ICON_PROVIDER = QFileIconProvider()
_ICON_PX = 16


def composer_chip_label(path: str) -> str:
    """칩 표시명 — @ref는 basename, 로컬 경로는 파일/폴더명."""
    p = (path or "").strip()
    if not p:
        return ""
    if p.startswith("@"):
        tail = p[1:].split(":")[0]
        name = Path(tail.replace("/", os.sep)).name
        return name or tail
    return Path(p).name or p


def composer_chip_icon(path: str, *, workspace_root: str = "") -> QPixmap:
    """칩 아이콘 — OS 파일 아이콘(QFileIconProvider)."""
    raw = (path or "").strip()
    fs_path = raw
    if raw.startswith("@"):
        rel = raw[1:].split(":")[0]
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
        label = QLabel(name)
        label.setToolTip(path)
        label.setStyleSheet("color: #e2e8f0; font-size: 11px;")

        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setFlat(True)
        btn.setStyleSheet("color: #94a3b8; border: none;")
        btn.clicked.connect(lambda _=False, p=path: self._remove(p))

        lay.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
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

    def _remove(self, path: str) -> None:
        self._paths = [p for p in self._paths if p != path]
        self._rebuild()
