"""이메일 워크스페이스 — Gmail식 메일 리스트/리더 + 아이리스 오브·채팅."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from iris.infrastructure.email_client import MailMessage, MailSummary
from iris.storage.email_accounts import EmailAccount
from iris.ui.chat.chat_panel import ChatComposerInput
from iris.ui.widgets.particle_visualizer import ParticleVisualizer
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisChatLog

_CATEGORY_TABS = ("기본", "프로모션", "소셜", "업데이트")


class _ComposeDialog(QDialog):
    def __init__(self, account: EmailAccount, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("메일 작성")
        self.setMinimumWidth(520)
        self._account = account

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._from_label = QLabel(account.address)
        self._to = QLineEdit()
        self._to.setPlaceholderText("받는 사람")
        self._subject = QLineEdit()
        self._subject.setPlaceholderText("제목")
        self._body = QPlainTextEdit()
        self._body.setPlaceholderText("본문")
        self._body.setMinimumHeight(180)
        form.addRow("보내는 사람", self._from_label)
        form.addRow("받는 사람", self._to)
        form.addRow("제목", self._subject)
        form.addRow("본문", self._body)
        lay.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Send | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Send).setText("보내기")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def payload(self) -> tuple[str, str, str]:
        return (
            self._to.text().strip(),
            self._subject.text().strip(),
            self._body.toPlainText(),
        )


class _MailRow(QWidget):
    """Gmail식 목록 한 줄 — 발신자 · 제목 — 스니펫 · 날짜."""

    def __init__(self, mail: MailSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        star = QLabel("☆")
        star.setStyleSheet("color: #64748b; font-size: 14px;")
        row.addWidget(star, 0)

        sender = QLabel(mail.sender)
        sender.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        sender.setMinimumWidth(150)
        sender.setMaximumWidth(180)
        sender.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(sender, 0)

        subject = mail.subject
        snippet = (mail.snippet or "").strip()
        text = f"{subject}  —  {snippet}" if snippet else subject
        body = QLabel(text)
        body.setStyleSheet("color: #94a3b8;")
        body.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(body, 1)

        date = QLabel(mail.date)
        date.setStyleSheet("color: #64748b; font-size: 11px;")
        date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(date, 0)


class _EmailIrisPanel(QWidget):
    """우측 — 아이리스 오브 + 이메일 전용 채팅."""

    chat_send = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailIrisPanel")

        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        # 구체 영역/위치는 우측 상단으로 유지하되 구체 자체를 크게 렌더링.
        # ponytail: fit-cap 때문에 슬롯을 키워야 실제로 커진다(오버플로우/클리핑 회피).
        self.orb = ParticleVisualizer(self)
        self.orb.setMinimumHeight(300)
        self.orb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.orb.set_size_scale(3.0)
        col.addWidget(self.orb, 0)

        self._log = WorkspaceIrisChatLog("EmailChatLog")
        col.addWidget(self._log, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = ChatComposerInput()
        self._input.setObjectName("EmailChatInput")
        self._input.setPlaceholderText("이메일 업무를 요청하세요 (예: 이 메일 답장 초안)")
        self._input.setStyleSheet(
            """
            QPlainTextEdit#EmailChatInput {
                background-color: rgba(15, 23, 42, 0.85);
                color: #ffffff;
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 16px;
                padding: 6px 12px;
            }
            QPlainTextEdit#EmailChatInput:focus { border-color: rgba(56, 189, 248, 0.6); }
            """
        )
        self._input.submit_requested.connect(self._emit_send)
        self._send = QPushButton("↑")
        self._send.setFixedSize(30, 30)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setStyleSheet(
            """
            QPushButton {
                background-color: #4f46e5; color: #fff; border: none;
                border-radius: 15px; font-size: 15px; font-weight: 700;
            }
            QPushButton:hover { background-color: #6366f1; }
            """
        )
        self._send.clicked.connect(self._emit_send)
        input_row.addWidget(self._input, 1, Qt.AlignmentFlag.AlignBottom)
        input_row.addWidget(self._send, 0, Qt.AlignmentFlag.AlignBottom)
        col.addLayout(input_row)

    def _emit_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.chat_send.emit(text)

    def append_user(self, text: str) -> None:
        self._log.append_user(text)

    def append_iris_chunk(self, text: str) -> None:
        self._log.append_iris_chunk(text)

    def end_iris(self, final_text: str | None = None) -> None:
        self._log.end_iris(final_text)

    def append_iris_tool(self, text: str) -> None:
        self._log.append_iris_tool(text)

    def append_iris_error(self, text: str) -> None:
        self._log.append_iris_error(text)

    def set_orb_state(self, state_name: str) -> None:
        self.orb.set_state(state_name)


class EmailWorkspacePage(QWidget):
    """중앙 메일 리스트/리더 + 우측 아이리스 패널."""

    mail_selected = pyqtSignal(str)  # uid
    refresh_requested = pyqtSignal()
    compose_requested = pyqtSignal(str, str, str)  # to, subject, body
    email_chat_send = pyqtSignal(str)
    category_selected = pyqtSignal(int)  # 카테고리 탭 index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailWorkspacePage")
        self._mails: list[MailSummary] = []
        self._current_account: EmailAccount | None = None
        self._current_message: MailMessage | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)

        splitter.addWidget(self._build_center())

        self.iris_panel = _EmailIrisPanel()
        self.iris_panel.setMinimumWidth(240)
        self.iris_panel.setMaximumWidth(380)
        self.iris_panel.chat_send.connect(self.email_chat_send.emit)
        splitter.addWidget(self.iris_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 320])
        outer.addWidget(splitter)

    # ---- 중앙(검색 + 탭 + 리스트/리더) ----
    def _build_center(self) -> QWidget:
        center = QWidget()
        center.setObjectName("WorkspacePanel")
        lay = QVBoxLayout(center)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._search = QLineEdit()
        self._search.setObjectName("EmailSearch")
        self._search.setPlaceholderText("메일 검색")
        self._search.setStyleSheet(
            """
            QLineEdit#EmailSearch {
                background-color: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 18px; padding: 8px 14px; color: #e2e8f0;
            }
            QLineEdit#EmailSearch:focus { border-color: rgba(56, 189, 248, 0.55); }
            """
        )
        self._search.textChanged.connect(self._apply_filter)
        self._refresh_btn = QPushButton("새로고침")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        top.addWidget(self._search, 1)
        top.addWidget(self._refresh_btn, 0)
        lay.addLayout(top)

        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        for i, name in enumerate(_CATEGORY_TABS):
            btn = QPushButton(name)
            btn.setObjectName("EmailCategoryTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(i == 0)
            btn.setStyleSheet(
                """
                QPushButton#EmailCategoryTab {
                    background: transparent; border: none; outline: none;
                    border-bottom: 2px solid transparent;
                    padding: 6px 14px; color: #94a3b8; font-weight: 600;
                }
                QPushButton#EmailCategoryTab:checked {
                    color: #38bdf8; border-bottom: 2px solid #38bdf8;
                }
                QPushButton#EmailCategoryTab:hover { color: #e2e8f0; }
                """
            )
            self._tab_group.addButton(btn, i)
            tabs.addWidget(btn, 0)
        tabs.addStretch(1)
        self._tab_group.idClicked.connect(self._on_tab_clicked)
        lay.addLayout(tabs)

        self._status = QLabel("프로필에서 이메일 계정을 추가하세요.")
        self._status.setObjectName("PanelEmptyHint")
        lay.addWidget(self._status)

        self._stack = QStackedWidget()

        self._list = QListWidget()
        self._list.setObjectName("EmailCenterList")
        self._list.setStyleSheet(
            """
            QListWidget#EmailCenterList { background: transparent; border: none; outline: none; }
            QListWidget#EmailCenterList::item { border-bottom: 1px solid rgba(148,163,184,0.10); }
            QListWidget#EmailCenterList::item:selected { background: rgba(56, 189, 248, 0.12); }
            QListWidget#EmailCenterList::item:hover { background: rgba(148, 163, 184, 0.08); }
            """
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        self._stack.addWidget(self._list)

        reader = QWidget()
        reader_lay = QVBoxLayout(reader)
        reader_lay.setContentsMargins(0, 0, 0, 0)
        reader_lay.setSpacing(6)
        back = QPushButton("←  목록")
        back.setObjectName("IdeActivityBackButton")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        reader_lay.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        self._meta = QLabel("")
        self._meta.setObjectName("SectionTitle")
        self._meta.setWordWrap(True)
        reader_lay.addWidget(self._meta)
        # 실제 브라우저 엔진으로 렌더 → HTML·이미지·상호작용 정상 표시.
        self._body = QWebEngineView()
        self._body.setObjectName("EmailPreviewBody")
        # 배경 흰색 제거 → 사이버스페이스 배경이 비치도록 투명 처리.
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._body.setStyleSheet("background: transparent;")
        self._body.page().setBackgroundColor(Qt.GlobalColor.transparent)
        reader_lay.addWidget(self._body, 1)
        self._stack.addWidget(reader)

        lay.addWidget(self._stack, 1)
        return center

    # ---- 외부 API (main_window에서 사용) ----
    def set_current_account(self, account: EmailAccount | None) -> None:
        self._current_account = account

    def current_account(self) -> EmailAccount | None:
        return self._current_account

    def current_message(self) -> MailMessage | None:
        return self._current_message

    def set_loading(self, loading: bool) -> None:
        self._refresh_btn.setEnabled(not loading)
        if loading:
            self._status.setText("메일 불러오는 중…")

    def set_mails(self, items: list[MailSummary]) -> None:
        self._mails = list(items)
        self._render_list(self._mails)
        self._stack.setCurrentIndex(0)
        if self._mails:
            self._status.setText(f"{len(self._mails)}통")
        else:
            self.show_empty_inbox_hint()

    def _render_list(self, items: list[MailSummary]) -> None:
        self._list.clear()
        for mail in items:
            row = QListWidgetItem()
            row.setData(256, mail.uid)
            widget = _MailRow(mail)
            row.setSizeHint(widget.sizeHint())
            self._list.addItem(row)
            self._list.setItemWidget(row, widget)

    def show_message(self, msg: MailMessage) -> None:
        self._current_message = msg
        self._meta.setText(msg.subject)
        header = html.escape(
            f"보낸 사람: {msg.sender}    받는 사람: {msg.to}    날짜: {msg.date}"
        )
        if msg.html:
            content = msg.html
        else:
            content = (
                "<pre style='white-space:pre-wrap; word-wrap:break-word;'>"
                f"{html.escape(msg.body)}</pre>"
            )
        doc = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "</head><body style='margin:0; padding:12px; font-family:sans-serif; "
            "color:#e2e8f0; background:transparent;'>"
            f"<div style='color:#94a3b8; font-size:12px; padding-bottom:8px; "
            f"border-bottom:1px solid rgba(148,163,184,0.25); margin-bottom:12px;'>{header}</div>"
            f"{content}</body></html>"
        )
        self._body.setHtml(doc)
        self._stack.setCurrentIndex(1)

    def show_error(self, text: str) -> None:
        self._status.setText(text)
        self._body.setHtml("")

    def show_empty_inbox_hint(self) -> None:
        self._status.setText("메일이 없습니다.")
        self._body.setHtml("")

    def open_compose(self, account: EmailAccount) -> None:
        dlg = _ComposeDialog(account, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        to, subject, body = dlg.payload()
        if not to:
            self._status.setText("받는 사람을 입력하세요.")
            return
        self.compose_requested.emit(to, subject, body)

    # ---- 내부 이벤트 ----
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        uid = item.data(256)
        if uid:
            self.mail_selected.emit(str(uid))

    def _on_tab_clicked(self, index: int) -> None:
        self.category_selected.emit(index)

    def set_category_index(self, index: int) -> None:
        """탭 하이라이트만 변경(로드 트리거 없음)."""
        btn = self._tab_group.button(index)
        if btn is not None:
            btn.setChecked(True)

    def set_status_text(self, text: str) -> None:
        self._status.setText(text)

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._render_list(self._mails)
            return
        filtered = [
            m
            for m in self._mails
            if query in m.subject.lower()
            or query in m.sender.lower()
            or query in (m.snippet or "").lower()
        ]
        self._render_list(filtered)
        self._status.setText(f"검색 결과 {len(filtered)}통")
