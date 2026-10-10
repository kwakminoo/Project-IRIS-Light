"""Immediate, durable chat-only typography controls."""
from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QGroupBox, QFormLayout, QComboBox, QSpinBox, QTextEdit, QPushButton, QLabel, QCompleter
from iris.ui.chat.typography import (
    TYPING_CHARS_PER_SEC_MAX,
    TYPING_CHARS_PER_SEC_MIN,
    manager,
    defaults,
    Typography,
    font,
)
from iris.ui.chat.chat_renderer import render_user_message, render_iris_message


def build_typography_box(db):
    box = QGroupBox("채팅 폰트")
    form = QFormLayout(box)
    form.addRow(QLabel("메인·IDE 채팅에 즉시 적용하고 자동 저장합니다. 설정창 UI 폰트는 유지됩니다."))
    families = sorted(QFontDatabase.families(), key=str.casefold)
    p = manager.get()
    controls = {}
    for key, label in (("chat_font_family", "채팅 폰트"), ("chat_font_size", "채팅 글자 크기 (px)"),
                       ("code_font_family", "코드 폰트"), ("code_font_size", "코드 글자 크기 (px)")):
        if key.endswith("family"):
            control = QComboBox()
            control.addItems(families)
            control.setEditable(True)
            control.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            control.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            control.completer().setFilterMode(Qt.MatchFlag.MatchContains)
            control.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            control.setCurrentText(getattr(p, key))
        else:
            control = QSpinBox()
            control.setRange(10, 28)
            control.setValue(getattr(p, key))
        control.setObjectName(key)
        controls[key] = control
        form.addRow(label, control)
    speed = QSpinBox()
    speed.setRange(TYPING_CHARS_PER_SEC_MIN, TYPING_CHARS_PER_SEC_MAX)
    speed.setValue(p.typing_chars_per_sec)
    speed.setSuffix(" 글자/초")
    speed.setObjectName("typing_chars_per_sec")
    speed.setToolTip("아이리스 답변이 한 글자씩 나오는 속도입니다.")
    controls["typing_chars_per_sec"] = speed
    form.addRow("타이핑 속도", speed)
    preview = QTextEdit()
    preview.setObjectName("chat_font_preview")
    preview.setReadOnly(True)
    preview.setMinimumHeight(190)
    form.addRow("미리보기", preview)
    reset = QPushButton("기본값으로 복원")
    reset.setObjectName("restore_chat_typography")
    form.addRow(reset)

    def refresh():
        preview.setFont(font())
        preview.document().setDefaultFont(font())
        preview.setHtml(render_user_message("안녕하세요. IRIS 폰트 테스트입니다.\nABC abc 123\n가나다라마바사") +
                        render_iris_message("## Markdown 제목\n- 리스트 테스트\n\n```python\nprint('안녕하세요 ABC 123')\n```\n\n|항목|값|\n|---|---|\n|한글|ABC 123|"))

    def apply():
        values = {key: (c.currentText() if key.endswith("family") else c.value()) for key, c in controls.items()}
        if values["chat_font_family"] not in families or values["code_font_family"] not in families:
            return  # A partially typed search is not a selected installed font.
        manager.apply(Typography(**values), db)
        refresh()

    def restore():
        p = defaults()
        for key, c in controls.items():
            blocker = QSignalBlocker(c)
            if key.endswith("family"):
                c.setCurrentText(getattr(p, key))
            else:
                c.setValue(getattr(p, key))
            del blocker
        apply()

    for key, c in controls.items():
        (c.currentTextChanged if key.endswith("family") else c.valueChanged).connect(apply)
    reset.clicked.connect(restore)
    refresh()
    return box
