"""사용자 프로필 편집 창."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.database import Database
from iris.storage.email_accounts import (
    add_email_account,
    load_email_accounts,
    remove_email_account,
)
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.ui.email_workers import EmailVerifyWorker

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
    ("email", "자주 쓰는 이메일", "예: name@example.com (표시용)", False),
)


class UserProfileDialog(QDialog):
    """사용자 프로필 + 이메일 계정 입력·저장."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._wiki = IrisWiki()
        self._accounts = load_email_accounts(db)
        self._verify_worker: EmailVerifyWorker | None = None
        self.setWindowTitle("사용자 프로필")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Noto Sans KR", "Segoe UI Variable", "Segoe UI", "Malgun Gothic";
                font-size: 13px;
            }
            QLineEdit, QTextEdit, QListWidget {
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

        hint = QLabel(
            "입력한 내용은 이 PC의 Iris Light DB와 Iris Wiki(~/.iris-light/iris-wiki)에만 저장됩니다. "
            "이메일 비밀번호는 앱/애플리케이션 비밀번호를 사용하세요."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setSpacing(16)

        form_wrap = QWidget()
        form = QFormLayout(form_wrap)
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
        content_lay.addWidget(form_wrap)

        email_box = QGroupBox("이메일 계정 (Gmail · Naver 등)")
        email_lay = QVBoxLayout(email_box)
        email_lay.addWidget(
            QLabel("IMAP/SMTP로 직접 연결합니다. 일반 로그인 비밀번호 대신 앱 비밀번호를 입력하세요.")
        )

        self._account_list = QListWidget()
        self._account_list.setMaximumHeight(120)
        email_lay.addWidget(self._account_list)

        add_form = QFormLayout()
        self._new_label = QLineEdit()
        self._new_label.setPlaceholderText("예: 개인 Gmail")
        self._new_address = QLineEdit()
        self._new_address.setPlaceholderText("예: you@gmail.com")
        self._new_password = QLineEdit()
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password.setPlaceholderText("앱/애플리케이션 비밀번호")
        add_form.addRow("표시 이름", self._new_label)
        add_form.addRow("이메일 주소", self._new_address)
        add_form.addRow("비밀번호", self._new_password)
        email_lay.addLayout(add_form)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("계정 추가")
        self._add_btn.clicked.connect(self._add_account)
        self._remove_btn = QPushButton("선택 삭제")
        self._remove_btn.clicked.connect(self._remove_selected_account)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch(1)
        email_lay.addLayout(btn_row)
        content_lay.addWidget(email_box)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._reload_account_list()

    def _reload_account_list(self) -> None:
        self._account_list.clear()
        for acc in self._accounts:
            self._account_list.addItem(QListWidgetItem(acc.display_name))

    def _add_account(self) -> None:
        address = self._new_address.text().strip()
        password = self._new_password.text()
        label = self._new_label.text().strip()
        if not address or "@" not in address:
            QMessageBox.warning(self, "이메일 계정", "올바른 이메일 주소를 입력하세요.")
            return
        if not password:
            QMessageBox.warning(self, "이메일 계정", "앱/애플리케이션 비밀번호를 입력하세요.")
            return
        self._add_btn.setEnabled(False)
        worker = EmailVerifyWorker(address, password, parent=self)
        self._verify_worker = worker
        worker.finished_ok.connect(lambda: self._on_verify_ok(address, password, label))
        worker.failed.connect(self._on_verify_failed)
        worker.start()

    def _on_verify_ok(self, address: str, password: str, label: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        add_email_account(self._db, address, password, label=label)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()
        self._new_address.clear()
        self._new_password.clear()
        self._new_label.clear()
        QMessageBox.information(self, "이메일 계정", f"{address} 연결 확인됨 — 저장 목록에 추가했습니다.")

    def _on_verify_failed(self, err: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        QMessageBox.warning(
            self,
            "이메일 계정",
            f"연결에 실패했습니다.\n\n{err[:400]}\n\n"
            "IMAP/SMTP 사용·2단계 인증·앱 비밀번호를 확인하세요.",
        )

    def _remove_selected_account(self) -> None:
        row = self._account_list.currentRow()
        if row < 0 or row >= len(self._accounts):
            return
        acc = self._accounts[row]
        remove_email_account(self._db, acc.id)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()

    def _save(self) -> None:
        data: dict[str, str] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, QTextEdit):
                data[key] = widget.toPlainText().strip()
            else:
                data[key] = widget.text().strip()
        profile = UserProfile(**data)
        save_user_profile(self._db, profile)
        self._wiki.sync_profile_markdown(data)
        self._wiki.sync_email_accounts_index(
            [{"address": a.address, "label": a.label} for a in self._accounts]
        )
        self.accept()
