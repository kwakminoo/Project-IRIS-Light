from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from iris.storage.memory import MemoryStore
from iris.ui.settings.hud_dialog import run_hud_confirm


def build_memory_box(db, context) -> QGroupBox:
    store = MemoryStore(db)
    box = QGroupBox("Iris 기억")
    lay = QVBoxLayout(box)
    enabled = QCheckBox("로컬 Ollama 채팅에서 기억 사용")
    enabled.setChecked(store.enabled(context))
    enabled.toggled.connect(lambda on: store.set_enabled(context, on))
    lay.addWidget(enabled)
    hint = QLabel("저장·수정·삭제에는 직접 승인이 필요합니다. 이 섹션의 변경은 즉시 적용됩니다.")
    hint.setWordWrap(True)
    lay.addWidget(hint)
    query = QLineEdit()
    query.setPlaceholderText("현재 범위의 기억 검색")
    query.setAccessibleName("기억 검색")
    lay.addWidget(query)
    records = QListWidget()
    records.setAccessibleName("저장된 기억")
    records.setMaximumHeight(160)
    lay.addWidget(records)
    editor = QPlainTextEdit()
    editor.setAccessibleName("선택한 기억의 내용")
    editor.setMaximumHeight(110)
    lay.addWidget(editor)
    buttons = QHBoxLayout()
    update = QPushButton("수정 적용")
    delete = QPushButton("기억 삭제")
    buttons.addWidget(update)
    buttons.addWidget(delete)
    lay.addLayout(buttons)
    status = QLabel()
    status.setWordWrap(True)
    status.setTextFormat(Qt.TextFormat.PlainText)
    lay.addWidget(status)

    def selected():
        item = records.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select(_current=None, _previous=None):
        row = selected()
        editor.setPlainText(row["content"] if row else "")
        editor.setEnabled(bool(row))
        update.setEnabled(bool(row))
        delete.setEnabled(bool(row))

    def refresh(_query=None):
        records.clear()
        for row in store.search(context, query.text(), management=True, limit=100):
            label = " ".join(row["content"].split())
            item = QListWidgetItem(f"[{row['scope']}] {label[:100]}")
            item.setData(Qt.ItemDataRole.UserRole, row)
            records.addItem(item)
        select()

    def change(remove=False):
        row = selected()
        if row is None:
            return
        if remove and not run_hud_confirm(
            None, title="기억 삭제", body=row["content"][:160],
            hint="선택한 기억을 삭제합니다.", badge="DELETE", ok_text="삭제", destructive=True,
        ):
            return
        try:
            store.change(context, row["id"], row["revision"],
                         content=None if remove else editor.toPlainText(), management=True)
        except ValueError as exc:
            status.setText(str(exc))
            return
        refresh()
        status.setText("기억을 삭제했습니다." if remove else "기억을 수정했습니다.")

    records.currentItemChanged.connect(select)
    query.textChanged.connect(refresh)
    update.clicked.connect(lambda: change())
    delete.clicked.connect(lambda: change(True))
    refresh()
    return box
