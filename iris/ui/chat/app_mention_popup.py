"""Tiny composer popup for `@app` mention completion.

Owns: list apps under the input and emit the chosen directory entry.
Does not: parse mentions or open App Host.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from iris.apps.directory import AppDirectoryEntry


class AppMentionPopup(QListWidget):
    chosen = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppMentionPopup")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaximumHeight(160)
        self.setMinimumWidth(220)
        self.hide()
        self.itemClicked.connect(self._on_item_clicked)
        self.setStyleSheet(
            """
            QListWidget#AppMentionPopup {
                background: rgba(15, 23, 42, 0.96);
                color: #e2e8f0;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget#AppMentionPopup::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QListWidget#AppMentionPopup::item:selected {
                background: rgba(56, 189, 248, 0.28);
            }
            """
        )

    def set_entries(self, entries: list[AppDirectoryEntry]) -> None:
        self.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry.id}  ·  {entry.title}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.addItem(item)
        if self.count() > 0:
            self.setCurrentRow(0)

    def current_entry(self) -> AppDirectoryEntry | None:
        item = self.currentItem()
        if item is None:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, AppDirectoryEntry) else None

    def accept_current(self) -> bool:
        entry = self.current_entry()
        if entry is None:
            return False
        self.chosen.emit(entry)
        self.hide()
        return True

    def move_selection(self, delta: int) -> None:
        if self.count() <= 0:
            return
        row = max(0, min(self.currentRow() + delta, self.count() - 1))
        self.setCurrentRow(row)

    def place_above(self, anchor: QWidget) -> None:
        if self.count() <= 0:
            self.hide()
            return
        row_h = max(24, self.sizeHintForRow(0))
        height = min(160, row_h * self.count() + 10)
        self.setFixedHeight(height)
        width = max(220, anchor.width())
        self.setFixedWidth(width)
        top_left = anchor.mapToGlobal(anchor.rect().topLeft())
        self.move(top_left.x(), top_left.y() - height - 4)
        self.show()
        self.raise_()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, AppDirectoryEntry):
            self.chosen.emit(entry)
            self.hide()

    def handle_key(self, event: QKeyEvent) -> bool:
        if not self.isVisible() or self.count() <= 0:
            return False
        key = event.key()
        if key in (Qt.Key.Key_Up,):
            self.move_selection(-1)
            return True
        if key in (Qt.Key.Key_Down,):
            self.move_selection(1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            return self.accept_current()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return True
        return False
