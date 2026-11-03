"""이메일 워크스페이스 — Gmail식 메일 리스트/리더 + 아이리스 오브·채팅."""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from iris.infrastructure.email_client import MAIL_PAGE_SIZE, MailMessage, MailSummary
from iris.storage.email_accounts import EmailAccount
from iris.ui.workspaces.workspace_iris_chat import (
    install_companion_shell,
    mount_chat_host,
    shift_chat_column,
)

_CATEGORY_TABS = ("기본", "프로모션", "소셜", "업데이트")


def mail_date_group_label(date_str: str, *, today: date | None = None) -> str:
    """목록 날짜 구분선용 라벨 (오늘 / 어제 / N월 N일)."""
    today = today or date.today()
    raw = (date_str or "").strip()
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return raw[:16] if raw else "날짜 없음"
    if d == today:
        return "오늘"
    if d == today - timedelta(days=1):
        return "어제"
    if d.year == today.year:
        return f"{d.month}월 {d.day}일"
    return f"{d.year}년 {d.month}월 {d.day}일"


def mail_row_time_label(date_str: str) -> str:
    """날짜 그룹이 있을 때 행 오른쪽에 보일 시각."""
    raw = (date_str or "").strip()
    if len(raw) >= 16 and raw[10] == " ":
        return raw[11:16]
    return raw[:16]


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


class _CircularSpinner(QWidget):
    """안드로이드식 원형 인디케이터 — 텍스트 없이 호만 회전."""

    def __init__(self, parent: QWidget | None = None, *, size: int = 40) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QPen(QColor(148, 163, 184, 55))
        track.setWidthF(3.2)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        m = 3
        rect = QRect(m, m, self._size - 2 * m, self._size - 2 * m)
        p.drawArc(rect, 0, 360 * 16)
        arc = QPen(QColor(56, 189, 248))
        arc.setWidthF(3.2)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc)
        p.drawArc(rect, -self._angle * 16, 90 * 16)
        p.end()


class _MailLoadingOverlay(QWidget):
    """메일 영역 회색 오버레이 + 중앙 원형 스피너 (문구 없음)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("EmailLoadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#EmailLoadingOverlay { background: rgba(30, 41, 59, 0.55); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._spinner = _CircularSpinner(self, size=44)
        row.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.hide()

    def set_active(self, active: bool) -> None:
        if active:
            self.show()
            self.raise_()
            self._spinner.start()
        else:
            self._spinner.stop()
            self.hide()


class _DateHeader(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 4)
        title = QLabel(label)
        title.setStyleSheet(
            "color: #38bdf8; font-size: 12px; font-weight: 700; letter-spacing: 0.3px;"
        )
        lay.addWidget(title)
        lay.addStretch(1)


class _MailRow(QWidget):
    """Gmail식 목록 한 줄 — 발신자 · 제목 — 스니펫 · 시각."""

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

        date = QLabel(mail_row_time_label(mail.date))
        date.setStyleSheet("color: #64748b; font-size: 11px;")
        date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(date, 0)


class EmailWorkspacePage(QWidget):
    """중앙 메일 리스트/리더 + 우측 아이리스 패널."""

    mail_selected = pyqtSignal(str)  # uid
    refresh_requested = pyqtSignal()
    compose_requested = pyqtSignal(str, str, str)  # to, subject, body
    email_chat_send = pyqtSignal(str, list)
    category_selected = pyqtSignal(int)  # 카테고리 탭 index
    load_more_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailWorkspacePage")
        self._mails: list[MailSummary] = []
        self._current_account: EmailAccount | None = None
        self._current_message: MailMessage | None = None
        self._has_more = False
        self._loading_more = False
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # IDE와 동일: IdeUnifiedShell 8:2 (좌 메일 · 우 Companion)
        install_companion_shell(self, self._build_center(), root=outer)

    def place_chat_host(self, host: QWidget) -> None:
        mount_chat_host(self, host)

    def shift_chat_column(self, delta: int) -> None:
        shift_chat_column(self, delta)

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

        self._mail_area = QWidget()
        self._mail_area.setObjectName("EmailMailArea")
        area_lay = QVBoxLayout(self._mail_area)
        area_lay.setContentsMargins(0, 0, 0, 0)
        area_lay.setSpacing(0)

        self._stack = QStackedWidget(self._mail_area)

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
        self._list.verticalScrollBar().valueChanged.connect(self._on_list_scrolled)
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
        self._body: object | None = None
        self._body_slot = QWidget()
        self._body_slot_lay = QVBoxLayout(self._body_slot)
        self._body_slot_lay.setContentsMargins(0, 0, 0, 0)
        reader_lay.addWidget(self._body_slot, 1)
        self._stack.addWidget(reader)

        area_lay.addWidget(self._stack, 1)
        self._loading_overlay = _MailLoadingOverlay(self._mail_area)
        lay.addWidget(self._mail_area, 1)
        return center

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._loading_overlay.setGeometry(self._mail_area.rect())

    def _ensure_body_view(self):
        if self._body is not None:
            return self._body
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.setObjectName("EmailPreviewBody")
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        view.setStyleSheet("background: transparent;")
        view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self._body_slot_lay.addWidget(view)
        self._body = view
        return view

    # ---- 외부 API (main_window에서 사용) ----
    def set_current_account(self, account: EmailAccount | None) -> None:
        self._current_account = account

    def current_account(self) -> EmailAccount | None:
        return self._current_account

    def current_message(self) -> MailMessage | None:
        return self._current_message

    def current_mails(self) -> list[MailSummary]:
        return list(self._mails)

    def has_more(self) -> bool:
        return self._has_more

    def is_loading_more(self) -> bool:
        return self._loading_more

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._refresh_btn.setEnabled(not loading)
        self._loading_overlay.setGeometry(self._mail_area.rect())
        self._loading_overlay.set_active(loading)
        if loading:
            # 오버레이에는 문구 없음. 상태 라벨만 비움.
            self._status.setText("")

    def set_loading_more(self, loading: bool) -> None:
        self._loading_more = loading

    def set_mails(self, items: list[MailSummary], *, has_more: bool | None = None) -> None:
        self._mails = list(items)
        if has_more is None:
            self._has_more = len(items) >= MAIL_PAGE_SIZE
        else:
            self._has_more = has_more
        self._loading_more = False
        self._render_list(self._filtered_mails())
        self._stack.setCurrentIndex(0)
        if self._mails:
            self._status.setText(f"{len(self._mails)}통")
            QTimer.singleShot(0, self._maybe_request_more)
        else:
            self.show_empty_inbox_hint()

    def append_mails(self, items: list[MailSummary], *, has_more: bool | None = None) -> None:
        if not items:
            self._has_more = False if has_more is None else has_more
            self._loading_more = False
            return
        seen = {m.uid for m in self._mails}
        added = [m for m in items if m.uid not in seen]
        self._mails.extend(added)
        if has_more is None:
            self._has_more = len(items) >= MAIL_PAGE_SIZE
        else:
            self._has_more = has_more
        self._loading_more = False
        self._render_list(self._filtered_mails())
        if self._mails:
            self._status.setText(f"{len(self._mails)}통")
        # 목록이 짧아 스크롤이 없으면 다음 페이지를 이어서 요청
        QTimer.singleShot(0, self._maybe_request_more)

    def prepend_mails(self, items: list[MailSummary]) -> None:
        """IDLE 등으로 온 새 메일 — 목록 맨 위에만 삽입(전체 리로드 없음)."""
        if not items:
            return
        seen = {m.uid for m in self._mails}
        added = [m for m in items if m.uid not in seen]
        if not added:
            return
        self._mails = added + self._mails
        self._render_list(self._filtered_mails())
        if self._mails:
            self._status.setText(f"{len(self._mails)}통")

    def _filtered_mails(self) -> list[MailSummary]:
        query = self._search.text().strip().lower()
        if not query:
            return list(self._mails)
        return [
            m
            for m in self._mails
            if query in m.subject.lower()
            or query in m.sender.lower()
            or query in (m.snippet or "").lower()
        ]

    def _render_list(self, items: list[MailSummary]) -> None:
        self._list.clear()
        last_group = ""
        for mail in items:
            group = mail_date_group_label(mail.date)
            if group != last_group:
                header = QListWidgetItem()
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(256, "")
                widget = _DateHeader(group)
                header.setSizeHint(widget.sizeHint())
                self._list.addItem(header)
                self._list.setItemWidget(header, widget)
                last_group = group
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
        self._ensure_body_view().setHtml(doc)
        self._stack.setCurrentIndex(1)

    def show_error(self, text: str) -> None:
        self._status.setText(text)
        if self._body is not None:
            self._body.setHtml("")

    def show_empty_inbox_hint(self) -> None:
        self._status.setText("메일이 없습니다.")
        if self._body is not None:
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

    def _maybe_request_more(self) -> None:
        if self._loading or self._loading_more or not self._has_more:
            return
        bar = self._list.verticalScrollBar()
        # 스크롤이 없거나(목록이 짧음) 거의 끝이면 다음 페이지
        if bar.maximum() <= 0 or bar.value() >= bar.maximum() - 8:
            self.load_more_requested.emit()

    def _on_list_scrolled(self, _value: int) -> None:
        self._maybe_request_more()

    def set_category_index(self, index: int) -> None:
        """탭 하이라이트만 변경(로드 트리거 없음)."""
        btn = self._tab_group.button(index)
        if btn is not None:
            btn.setChecked(True)

    def set_status_text(self, text: str) -> None:
        self._status.setText(text)

    def _apply_filter(self, text: str) -> None:
        filtered = self._filtered_mails()
        self._render_list(filtered)
        query = text.strip()
        if query:
            self._status.setText(f"검색 결과 {len(filtered)}통")
        elif self._mails:
            self._status.setText(f"{len(self._mails)}통")
        else:
            self.show_empty_inbox_hint()
