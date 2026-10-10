"""메일 연결 안내 — 제공자별 순서와 설정 페이지.

비밀번호 IMAP으로 붙는 서비스만 둔다. Outlook/Hotmail은
OAuth만 허용해서 이 목록에 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.storage.database import Database
from iris.storage.email_accounts import (
    EmailAccount,
    add_email_account,
    load_email_accounts,
    remove_email_account,
)
from iris.ui.settings.hud_dialog import (
    configure_form,
    configure_hud_dialog,
    make_collapsible,
    make_form_label,
    make_hint,
)
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.workers.email_workers import EmailVerifyWorker


@dataclass(frozen=True)
class EmailConnectStep:
    summary: str
    url: str = ""
    link_label: str = "열기"


@dataclass(frozen=True)
class EmailProviderGuide:
    name: str
    domains: str
    steps: tuple[EmailConnectStep, ...]

    @property
    def steps_text(self) -> str:
        return "\n".join(f"{i}. {step.summary}" for i, step in enumerate(self.steps, 1))

    @property
    def open_url(self) -> str:
        for step in self.steps:
            if step.url:
                return step.url
        return ""

    @property
    def open_label(self) -> str:
        for step in self.steps:
            if step.url:
                return step.link_label
        return "열기"


def _open_url(url: str) -> None:
    if url:
        QDesktopServices.openUrl(QUrl(url))


EMAIL_PROVIDER_GUIDES: tuple[EmailProviderGuide, ...] = (
    EmailProviderGuide(
        name="Gmail (Google)",
        domains="gmail.com / googlemail.com",
        steps=(
            EmailConnectStep(
                "Google 계정에서 2단계 인증을 켭니다.",
                "https://myaccount.google.com/signinoptions/two-step-verification",
                "2단계 인증",
            ),
            EmailConnectStep(
                "앱 비밀번호에서 메일용 16자리 비밀번호를 만듭니다.",
                "https://myaccount.google.com/apppasswords",
                "앱 비밀번호",
            ),
            EmailConnectStep(
                "Gmail 설정 → 전달 및 POP/IMAP에서 IMAP 사용을 켭니다.",
                "https://mail.google.com/mail/u/0/#settings/fwdandpop",
                "IMAP 설정",
            ),
            EmailConnectStep("아래 칸에 Gmail 주소와 앱 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="네이버 메일",
        domains="naver.com",
        steps=(
            EmailConnectStep(
                "네이버 로그인 2단계 인증을 켜고 애플리케이션 비밀번호를 만듭니다.",
                "https://nid.naver.com/user2/help/myInfo?m=viewSecurity",
                "보안 설정",
            ),
            EmailConnectStep(
                "메일 환경설정에서 IMAP/SMTP를 사용함으로 저장합니다.",
                "https://mail.naver.com/v2/settings/imap",
                "IMAP 설정",
            ),
            EmailConnectStep("아래 칸에 네이버 주소와 애플리케이션 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="다음 메일 (Kakao)",
        domains="daum.net / hanmail.net",
        steps=(
            EmailConnectStep(
                "다음 메일에 로그인한 뒤 환경설정에서 IMAP 사용을 켭니다.",
                "https://mail.daum.net/",
                "다음 메일",
            ),
            EmailConnectStep(
                "카카오계정에 2단계 인증이 있으면 애플리케이션 비밀번호를 만듭니다. 없으면 계정 비밀번호를 씁니다.",
                "https://accounts.kakao.com/weblogin/account/security",
                "카카오 보안",
            ),
            EmailConnectStep("아래 칸에 daum 또는 hanmail 주소와 그 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="Yahoo 메일",
        domains="yahoo.com / ymail.com",
        steps=(
            EmailConnectStep(
                "Yahoo 계정 보안에서 앱 비밀번호를 만듭니다.",
                "https://login.yahoo.com/myaccount/security",
                "앱 비밀번호",
            ),
            EmailConnectStep("아래 칸에 Yahoo 주소와 앱 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="iCloud 메일",
        domains="icloud.com / me.com / mac.com",
        steps=(
            EmailConnectStep(
                "Apple ID 로그인 및 보안에서 앱 암호를 만듭니다.",
                "https://appleid.apple.com/account/manage",
                "앱 암호",
            ),
            EmailConnectStep("아래 칸에 iCloud 주소와 앱 암호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
)


class EmailAccountBox(QGroupBox):
    """설정·메일 안내가 같이 쓰는 계정 목록과 추가 칸."""

    accounts_changed = pyqtSignal()

    def __init__(self, db: Database | None, parent: QWidget | None = None) -> None:
        super().__init__("이메일 계정 (Gmail · Naver 등)", parent)
        self._db = db
        self._accounts: list[EmailAccount] = load_email_accounts(db) if db is not None else []
        self._verify_worker: EmailVerifyWorker | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "IMAP/SMTP로 직접 연결합니다. 일반 로그인 비밀번호 대신 앱 비밀번호를 입력하세요."
            )
        )
        lay.addWidget(build_email_connect_panel())
        self._account_list = QListWidget()
        self._account_list.setObjectName("EmailAccountList")
        self._account_list.setMinimumHeight(100)
        self._account_list.setMaximumHeight(140)
        lay.addWidget(self._account_list)

        add_form = QFormLayout()
        configure_form(add_form)
        self._new_label = QLineEdit()
        self._new_label.setObjectName("EmailLabelField")
        self._new_label.setPlaceholderText("예: 개인 Gmail")
        self._new_address = QLineEdit()
        self._new_address.setObjectName("EmailAddressField")
        self._new_address.setPlaceholderText("예: you@gmail.com")
        self._new_password = QLineEdit()
        self._new_password.setObjectName("EmailPasswordField")
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password.setPlaceholderText("앱/애플리케이션 비밀번호")
        for edit in (self._new_label, self._new_address, self._new_password):
            edit.setMinimumHeight(32)
        add_form.addRow(make_form_label("표시 이름"), self._new_label)
        add_form.addRow(make_form_label("이메일 주소"), self._new_address)
        add_form.addRow(make_form_label("비밀번호"), self._new_password)
        lay.addLayout(add_form)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("계정 추가")
        self._add_btn.setObjectName("EmailAddAccount")
        self._add_btn.clicked.connect(self._add_account)
        self._remove_btn = QPushButton("선택 삭제")
        self._remove_btn.setObjectName("EmailRemoveAccount")
        self._remove_btn.clicked.connect(self._remove_selected_account)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        self._reload_account_list()

    @property
    def accounts(self) -> list[EmailAccount]:
        return list(self._accounts)

    def _reload_account_list(self) -> None:
        self._account_list.clear()
        for acc in self._accounts:
            self._account_list.addItem(QListWidgetItem(acc.display_name))

    def _sync_wiki(self) -> None:
        # 위키 쓰기가 슬롯 밖으로 나가면 Qt가 앱을 죽인다.
        try:
            from iris.knowledge.iris_wiki import IrisWiki

            IrisWiki().sync_email_accounts_index(
                [{"address": a.address, "label": a.label} for a in self._accounts]
            )
        except Exception:
            return

    def _add_account(self) -> None:
        if self._db is None:
            return
        address = self._new_address.text().strip()
        password = self._new_password.text()
        label = self._new_label.text().strip()
        if not address or "@" not in address:
            QMessageBox.warning(self.window(), "이메일 계정", "올바른 이메일 주소를 입력하세요.")
            return
        if not password:
            QMessageBox.warning(self.window(), "이메일 계정", "앱/애플리케이션 비밀번호를 입력하세요.")
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
        if self._db is None:
            return
        add_email_account(self._db, address, password, label=label)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()
        self._new_address.clear()
        self._new_password.clear()
        self._new_label.clear()
        self._sync_wiki()
        self.accounts_changed.emit()
        QMessageBox.information(
            self.window(),
            "이메일 계정",
            f"{address} 연결 확인됨 — 저장 목록에 추가했습니다.",
        )

    def _on_verify_failed(self, err: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        QMessageBox.warning(
            self.window(),
            "이메일 계정",
            f"연결에 실패했습니다.\n\n{err[:400]}\n\n"
            "IMAP/SMTP 사용·2단계 인증·앱 비밀번호를 확인하세요.",
        )

    def _remove_selected_account(self) -> None:
        if self._db is None:
            return
        row = self._account_list.currentRow()
        if row < 0 or row >= len(self._accounts):
            return
        acc = self._accounts[row]
        remove_email_account(self._db, acc.id)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()
        self._sync_wiki()
        self.accounts_changed.emit()


class EmailConnectGuideDialog(QDialog):
    """메일함 진입 시 계정 없을 때. 본문은 설정 이메일 칸과 같다."""

    accounts_changed = pyqtSignal()

    def __init__(self, db: Database | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="메일 연결",
            min_w=640,
            min_h=560,
            default_w=720,
            default_h=680,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(TOKENS.spacing_sm)
        self._accounts_box = EmailAccountBox(db, self)
        self._accounts_box.accounts_changed.connect(self.accounts_changed)
        root.addWidget(make_collapsible(self._accounts_box), 1)

        action = QHBoxLayout()
        action.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        action.addWidget(close_btn)
        root.addLayout(action)


def build_email_connect_panel() -> QWidget:
    """설정 이메일 칸. 메일을 고르면 순서가 나오고, 항목·단계 버튼이 설정 페이지를 연다."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(
        make_hint(
            "연결할 메일을 누르면 그 서비스의 설정 페이지가 열리고, 아래에 따라 할 순서가 나옵니다. "
            "각 단계의 버튼으로도 그 페이지에 들어갈 수 있습니다."
        )
    )
    listing = QListWidget(host)
    listing.setCursor(Qt.CursorShape.PointingHandCursor)
    listing.setMaximumHeight(132)
    for guide in EMAIL_PROVIDER_GUIDES:
        item = QListWidgetItem(f"{guide.name}  ·  {guide.domains}")
        item.setData(Qt.ItemDataRole.UserRole, guide)
        item.setToolTip(guide.open_url)
        listing.addItem(item)
    lay.addWidget(listing)

    steps_host = QWidget(host)
    steps_lay = QVBoxLayout(steps_host)
    steps_lay.setContentsMargins(0, 0, 0, 0)
    steps_lay.setSpacing(4)
    lay.addWidget(steps_host)

    def _show(guide: EmailProviderGuide) -> None:
        while steps_lay.count():
            item = steps_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, step in enumerate(guide.steps, 1):
            row_w = QWidget(steps_host)
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            label = QLabel(f"{index}. {step.summary}", row_w)
            label.setObjectName("HudDialogHint")
            label.setWordWrap(True)
            row.addWidget(label, 1)
            if step.url:
                button = QPushButton(step.link_label, row_w)
                button.setFixedWidth(88)
                button.setToolTip(step.url)
                button.clicked.connect(lambda _=False, url=step.url: _open_url(url))
                row.addWidget(button, 0)
            steps_lay.addWidget(row_w)

    def _on_row(row: int) -> None:
        item = listing.item(row) if row >= 0 else None
        guide = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(guide, EmailProviderGuide):
            _show(guide)

    def _on_click(item: QListWidgetItem) -> None:
        guide = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(guide, EmailProviderGuide):
            _open_url(guide.open_url)

    listing.currentRowChanged.connect(_on_row)
    listing.itemClicked.connect(_on_click)
    if listing.count():
        listing.setCurrentRow(0)
    return host


def run_email_connect_guide(
    parent: QWidget | None = None,
    db: Database | None = None,
    on_changed=None,
) -> None:
    dialog = EmailConnectGuideDialog(db, parent)
    if on_changed is not None:
        dialog.accounts_changed.connect(on_changed)
    dialog.exec()


def _check_shared_account_box() -> None:
    """안내 창과 단독 칸이 같은 계정 추가 구성을 쓰는지."""
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "mail.db")
        try:
            dialog = EmailConnectGuideDialog(db)
            box = dialog.findChild(EmailAccountBox)
            assert box is not None
            for name in (
                "EmailAccountList",
                "EmailLabelField",
                "EmailAddressField",
                "EmailPasswordField",
                "EmailAddAccount",
                "EmailRemoveAccount",
            ):
                assert dialog.findChild(QWidget, name) is not None, name
            assert box._add_btn.text() == "계정 추가"
            standalone = EmailAccountBox(db)
            assert standalone._add_btn.text() == box._add_btn.text()
            dialog.close()
            standalone.close()
        finally:
            db.close()
    app.processEvents()


if __name__ == "__main__":
    assert len(EMAIL_PROVIDER_GUIDES) >= 4
    names = [guide.name for guide in EMAIL_PROVIDER_GUIDES]
    assert len(names) == len(set(names))
    gmail = EMAIL_PROVIDER_GUIDES[0]
    assert "google.com" in gmail.open_url
    assert "1. " in gmail.steps_text and gmail.steps[-1].url == ""
    assert all(step.url.startswith("https://") for guide in EMAIL_PROVIDER_GUIDES for step in guide.steps if step.url)
    _check_shared_account_box()
    print("email_connect_guide ok")
