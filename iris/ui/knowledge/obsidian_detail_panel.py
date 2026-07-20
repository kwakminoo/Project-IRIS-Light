"""Iris Wiki 좌측 — 노트 목록."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from iris.knowledge.iris_wiki import IrisWiki, IrisWikiNote


class ObsidianDetailPanel(QWidget):
    """Vault 노트 목록 — 선택 시 미리보기로 전달."""

    note_selected = pyqtSignal(str)
    view_mode_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianDetailPanel")
        self._wiki: IrisWiki | None = None
        self._notes: list[IrisWikiNote] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        title = QLabel("Iris Wiki")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)

        self._list = QListWidget(self)
        self._list.setObjectName("ObsidianNoteList")
        self._list.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._list, 1)

    def set_wiki(self, wiki: IrisWiki) -> None:
        self._wiki = wiki
        self.reload()

    def set_vault(self, wiki: IrisWiki) -> None:
        """하위 호환 alias."""
        self.set_wiki(wiki)

    def reload(self) -> None:
        self._list.clear()
        self._notes = self._wiki.list_notes() if self._wiki else []
        first_row = -1
        current_folder = ""
        for note in self._notes:
            if note.folder and note.folder != current_folder:
                current_folder = note.folder
                header = QListWidgetItem(current_folder.replace("/", " › "))
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(256, "header")
                self._list.addItem(header)
            item = QListWidgetItem(note.title)
            item.setData(256, note.rel_path)
            if first_row < 0:
                first_row = self._list.count()
            self._list.addItem(item)
        if self._notes and first_row >= 0:
            self._list.setCurrentRow(first_row)
            self.note_selected.emit(self._notes[0].rel_path)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        rel = item.data(256)
        if not rel or rel == "header":
            return
        self.note_selected.emit(str(rel))

    def select_note(self, rel_path: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(256) == rel_path:
                self._list.setCurrentItem(item)
                return
