"""사용자 프로필 편집 창."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.storage.database import Database
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile

_FIELD_ROWS: tuple[tuple[str, str, str, bool], ...] = (
    ("name", "이름", "예: 홍길동", False),
    ("occupation", "직업", "예: 소프트웨어 엔지니어", False),
    ("hobbies", "취미", "예: 게임, 독서, 등산", True),
    ("interests", "관심 분야", "예: AI, 자동화, 음악", True),
    (
        "work_tasks",
        "필요한 기능 · 주 업무/작업",
        "Iris Light에 기대하는 기능이나 자주 하는 업무를 적어 주세요.",
        True,
    ),
    ("age", "나이", "예: 28", False),
    ("gender", "성별", "예: 남성, 여성, 비공개", False),
    ("residence", "거주지", "예: 서울특별시", False),
    ("contact", "연락처", "예: 010-1234-5678", False),
    ("email", "자주 쓰는 이메일", "예: name@example.com", False),
)


class UserProfileDialog(QDialog):
    """사용자 프로필 입력·저장."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("사용자 프로필")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Noto Sans KR", "Segoe UI Variable", "Segoe UI", "Malgun Gothic";
                font-size: 13px;
            }
            QLineEdit, QTextEdit {
                background-color: #1a1c24;
                color: #ffffff;
                border: 1px solid #3f3f5f;
                border-radius: 4px;
                padding: 6px;
            }
            """
        )

        title = QLabel("사용자 프로필")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        hint = QLabel("입력한 내용은 이 PC의 Iris Light 데이터베이스에만 저장됩니다.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._fields: dict[str, QLineEdit | QTextEdit] = {}
        profile = load_user_profile(db)
        for key, label, placeholder, multiline in _FIELD_ROWS:
            if multiline:
                w: QLineEdit | QTextEdit = QTextEdit()
                w.setPlaceholderText(placeholder)
                w.setPlainText(getattr(profile, key, "") or "")
                w.setFixedHeight(72)
            else:
                w = QLineEdit()
                w.setPlaceholderText(placeholder)
                w.setText(getattr(profile, key, "") or "")
            self._fields[key] = w
            form.addRow(label, w)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        data: dict[str, str] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, QTextEdit):
                data[key] = widget.toPlainText().strip()
            else:
                data[key] = widget.text().strip()
        save_user_profile(self._db, UserProfile(**data))
        self.accept()
