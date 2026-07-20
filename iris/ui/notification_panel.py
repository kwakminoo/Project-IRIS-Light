"""알림 패널 — SQLite 쿨다운·무시·스누즈·대상 비활성."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.ui.glass_panel import wrap_glass_panel
from iris.ui.section_header import (
    SECTION_CONTENT_GAP,
    apply_section_panel_layout,
    make_section_header,
)
from iris.ui.theme_tokens import TOKENS

if TYPE_CHECKING:
    from iris.monitoring.notification_policy import NotificationPolicy

_SEVERITY_ICON = {
    "ERROR_DETECTED": ("⚠", TOKENS.error),
    "GENERATION_FAILED": ("⚠", TOKENS.error),
    "TASK_STALLED": ("⏱", TOKENS.warning),
    "APPROVAL_WAITING": ("!", TOKENS.warning),
    "USER_ACTION_REQUIRED": ("!", TOKENS.warning),
    "RESPONSE_READY": ("●", TOKENS.neon_cyan),
    "BUILD_NOT_STARTED": ("●", TOKENS.neon_blue),
    "NORMAL": ("●", TOKENS.success),
}


class _AlertPayload:
    """리스트 아이템에 실리는 알림 메타."""

    __slots__ = ("target_id", "category", "event_id", "focus_hint", "title", "message", "time_str")

    def __init__(
        self,
        target_id: int,
        category: str,
        event_id: int,
        focus_hint: str,
        title: str,
        message: str,
        time_str: str,
    ) -> None:
        self.target_id = target_id
        self.category = category
        self.event_id = event_id
        self.focus_hint = focus_hint
        self.title = title
        self.message = message
        self.time_str = time_str


class NotificationPanel(QWidget):
    """DB 정책 + 인메모리 보조. 우클릭: 무시·스누즈·대상 끄기."""

    action_requested = pyqtSignal(str, int, str, int)  # decision, target_id, category, event_id

    def __init__(
        self,
        cooldown_seconds: float = 90.0,
        policy: Optional["NotificationPolicy"] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NotificationPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._cooldown_sec = cooldown_seconds
        self._policy = policy

        inner = QWidget()
        inner.setObjectName("NotificationPanelInner")
        lay = QVBoxLayout(inner)
        apply_section_panel_layout(lay)
        lay.addWidget(make_section_header("ALERTS"))

        self._list = QListWidget()
        self._list.setObjectName("AlertsList")
        self._list.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        list_pal = self._list.palette()
        list_pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        self._list.setPalette(list_pal)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemClicked.connect(self._on_click)
        self._list.currentItemChanged.connect(lambda *_: self._sync_action_buttons())
        lay.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SECTION_CONTENT_GAP)
        self._btn_snooze = QPushButton("Snooze 15m")
        self._btn_snooze.setObjectName("AlertActionButton")
        self._btn_snooze.setToolTip("이 알림을 15분간 미룹니다")
        self._btn_snooze.clicked.connect(lambda: self._on_decision("snooze"))
        btn_row.addWidget(self._btn_snooze)
        self._btn_ignore = QPushButton("Ignore type")
        self._btn_ignore.setObjectName("AlertActionButton")
        self._btn_ignore.setToolTip("같은 유형의 알림을 더 이상 표시하지 않습니다")
        self._btn_ignore.clicked.connect(lambda: self._on_decision("ignore"))
        btn_row.addWidget(self._btn_ignore)
        self._btn_disable = QPushButton("Disable target")
        self._btn_disable.setObjectName("AlertActionButton")
        self._btn_disable.setToolTip("해당 모니터링 대상을 끕니다")
        self._btn_disable.clicked.connect(lambda: self._on_decision("disable_target"))
        btn_row.addWidget(self._btn_disable)
        lay.addLayout(btn_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(wrap_glass_panel(inner))

        self._sync_action_buttons()

    def set_policy(self, policy: "NotificationPolicy") -> None:
        self._policy = policy

    def add_note(self, text: str) -> None:
        self._list.addItem(text)

    def try_add_alert(
        self,
        target_id: int,
        category: str,
        title: str,
        message: str,
        focus_hint: str,
        event_id: int = 0,
    ) -> bool:
        """정책 통과 시 True (MonitorManager가 DB 쿨다운 처리 후 UI만 표시)."""
        time_str = QDateTime.currentDateTime().toString("HH:mm")
        icon, _color = _SEVERITY_ICON.get(category, ("●", TOKENS.text_secondary))
        summary = message.strip().split("\n")[0][:100] if message else ""
        line = f"{icon}  {time_str}  {title}\n    {summary}"
        item = QListWidgetItem(line)
        payload = _AlertPayload(
            target_id, category, event_id, focus_hint, title, message, time_str
        )
        item.setData(Qt.ItemDataRole.UserRole, payload)
        self._list.insertItem(0, item)
        while self._list.count() > 80:
            self._list.takeItem(self._list.count() - 1)
        self._list.setCurrentItem(item)
        self._sync_action_buttons()
        return True

    def _sync_action_buttons(self) -> None:
        enabled = self._current_payload() is not None
        for btn in (self._btn_snooze, self._btn_ignore, self._btn_disable):
            btn.setEnabled(enabled)

    def _current_payload(self) -> _AlertPayload | None:
        item = self._list.currentItem()
        if item is None and self._list.count() > 0:
            item = self._list.item(0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, _AlertPayload) else None

    def _on_decision(self, decision: str) -> None:
        p = self._current_payload()
        if p is None:
            return
        if self._policy:
            if decision == "ignore":
                self._policy.dismiss_permanently(p.target_id, p.category)
            elif decision == "snooze":
                self._policy.snooze(p.target_id, p.category, 15)
            elif decision == "disable_target":
                self._policy.disable_target(p.target_id)
            self._policy.log_notification(
                p.target_id,
                p.event_id or None,
                p.category,
                p.title,
                "",
                user_decision=decision,
            )
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)
        self._sync_action_buttons()
        self.action_requested.emit(decision, p.target_id, p.category, p.event_id)

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        self._list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Snooze 15m", lambda: self._on_decision("snooze"))
        menu.addAction("Ignore this type", lambda: self._on_decision("ignore"))
        menu.addAction("Disable target monitoring", lambda: self._on_decision("disable_target"))
        menu.exec(self._list.mapToGlobal(pos))

    def _on_click(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, _AlertPayload) and data.focus_hint.strip():
            from iris.automation import window_controller

            window_controller.focus_and_place(data.focus_hint.strip(), 40, 40, 1000, 700)
