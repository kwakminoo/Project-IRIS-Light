"""Composer 파일 첨부 칩 스트립."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class ComposerAttachmentStrip(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerAttachmentStrip")
        self._paths: list[str] = []
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 0, 8, 4)
        self._row.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hide()

    def paths(self) -> list[str]:
        return list(self._paths)

    def add_paths(self, paths: list[str]) -> None:
        for raw in paths:
            p = str(raw).strip()
            if not p or p in self._paths:
                continue
            self._paths.append(p)
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
        lay.setContentsMargins(8, 2, 4, 2)
        lay.setSpacing(4)
        name = Path(path).name or path
        label = QLabel(name)
        label.setToolTip(path)
        label.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setFlat(True)
        btn.setStyleSheet("color: #94a3b8; border: none;")
        btn.clicked.connect(lambda _=False, p=path: self._remove(p))
        lay.addWidget(label)
        lay.addWidget(btn)
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
