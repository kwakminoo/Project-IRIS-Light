"""Iris Wiki 좌측 — 폴더 접기/펼치기 트리."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris.knowledge.iris_wiki import IrisWiki, IrisWikiNote

_ROLE = Qt.ItemDataRole.UserRole
_FOLDER = "__folder__"


class ObsidianDetailPanel(QWidget):
    """Vault 노트 트리 — 폴더 클릭 시 접기/펼치기, 노트 클릭 시 미리보기."""

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

        self._tree = QTreeWidget(self)
        self._tree.setObjectName("ObsidianNoteTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setStyleSheet(
            """
            QTreeWidget#ObsidianNoteTree { background: transparent; border: none; }
            QTreeWidget#ObsidianNoteTree::item { padding: 4px 2px; color: #cbd5e1; }
            QTreeWidget#ObsidianNoteTree::item:selected {
                background: rgba(56, 189, 248, 0.12); color: #e0f2fe;
            }
            QTreeWidget#ObsidianNoteTree::item:hover { background: rgba(148, 163, 184, 0.10); }
            """
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._tree, 1)

    def set_wiki(self, wiki: IrisWiki) -> None:
        self._wiki = wiki
        self.reload()

    def set_vault(self, wiki: IrisWiki) -> None:
        """하위 호환 alias."""
        self.set_wiki(wiki)

    def reload(self) -> None:
        self._tree.clear()
        self._notes = self._wiki.list_notes() if self._wiki else []
        folder_items: dict[str, QTreeWidgetItem] = {}

        def ensure_folder(path: str) -> QTreeWidgetItem | None:
            path = (path or "").strip("/")
            if not path:
                return None
            if path in folder_items:
                return folder_items[path]
            parts = path.split("/")
            parent = ensure_folder("/".join(parts[:-1]))
            item = QTreeWidgetItem([parts[-1]])
            item.setData(0, _ROLE, _FOLDER)
            if parent is None:
                self._tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            folder_items[path] = item
            return item

        first: QTreeWidgetItem | None = None
        for note in self._notes:
            parent = ensure_folder(note.folder)
            leaf = QTreeWidgetItem([note.title])
            leaf.setData(0, _ROLE, note.rel_path)
            if parent is None:
                self._tree.addTopLevelItem(leaf)
            else:
                parent.addChild(leaf)
            if first is None:
                first = leaf

        self._tree.expandAll()
        if first is not None:
            self._tree.setCurrentItem(first)
            self.note_selected.emit(str(first.data(0, _ROLE)))

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, _ROLE)
        if data == _FOLDER:
            item.setExpanded(not item.isExpanded())
            return
        if data:
            self.note_selected.emit(str(data))

    def select_note(self, rel_path: str) -> None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ROLE) == rel_path:
                    return child
                found = walk(child)
                if found is not None:
                    return found
            return None

        root = self._tree.invisibleRootItem()
        target = walk(root)
        if target is not None:
            self._tree.setCurrentItem(target)
