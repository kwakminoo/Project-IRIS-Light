"""Workspace 전환·퀵런치 아이콘 — HUD 정사각형 버튼 그리드."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from iris.ui.hud_quick_launch_icons import (
    HUD_ICON_BTN_PX,
    hud_icon_size,
    hud_quick_launch_icon,
)


@dataclass
class WorkspaceAction:
    action_id: str
    icon_kind: str
    tooltip: str
    callback: Callable[[], None] | None


class WorkspaceActionPanel(QWidget):
    """사이드바 하단 — 3열 정사각형 HUD 아이콘 그리드."""

    _GRID_COLS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceActionPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 8)
        root.setSpacing(0)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(6)
        root.addLayout(self._grid)

        self._buttons: dict[str, QPushButton] = {}
        self._actions: dict[str, WorkspaceAction] = {}
        self._slot = 0
        self._default_callback: Callable[[], None] | None = None

    def set_default_callback(self, callback: Callable[[], None] | None) -> None:
        """선택된 아이콘 재클릭 시 호출 — 보통 assistant 기본 화면 복귀."""
        self._default_callback = callback

    def _invoke_icon_action(self, action_id: str, callback: Callable[[], None]) -> None:
        btn = self._buttons.get(action_id)
        if btn is not None and btn.property("active") is True and self._default_callback is not None:
            self._default_callback()
            return
        callback()

    def add_icon_action(
        self,
        *,
        action_id: str,
        icon_kind: str,
        tooltip: str,
        callback: Callable[[], None] | None = None,
    ) -> None:
        if action_id in self._buttons:
            self.update_action(action_id, icon_kind=icon_kind, tooltip=tooltip)
            self._actions[action_id] = WorkspaceAction(action_id, icon_kind, tooltip, callback)
            return

        btn = QPushButton()
        btn.setObjectName("HudIconButton")
        btn.setToolTip(tooltip)
        btn.setProperty("active", False)
        btn.setProperty("iconKind", icon_kind)
        btn.setFixedSize(HUD_ICON_BTN_PX, HUD_ICON_BTN_PX)
        btn.setIconSize(hud_icon_size())
        btn.setIcon(hud_quick_launch_icon(icon_kind))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback is not None:
            btn.clicked.connect(
                lambda _checked=False, aid=action_id, cb=callback: self._invoke_icon_action(aid, cb)
            )

        row, col = divmod(self._slot, self._GRID_COLS)
        self._slot += 1
        self._grid.addWidget(btn, row, col)

        self._buttons[action_id] = btn
        self._actions[action_id] = WorkspaceAction(action_id, icon_kind, tooltip, callback)

    def update_action(
        self,
        action_id: str,
        *,
        icon_kind: str | None = None,
        tooltip: str | None = None,
        active: bool | None = None,
    ) -> None:
        btn = self._buttons.get(action_id)
        if btn is None:
            return
        kind = icon_kind or btn.property("iconKind") or "ide"
        if icon_kind is not None:
            btn.setProperty("iconKind", icon_kind)
        if tooltip is not None:
            btn.setToolTip(tooltip)
        is_active = active if active is not None else btn.property("active") is True
        if active is not None:
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        btn.setIcon(hud_quick_launch_icon(kind, active=is_active))
        action = self._actions.get(action_id)
        if action is not None:
            self._actions[action_id] = WorkspaceAction(
                action_id,
                kind,
                tooltip or action.tooltip,
                action.callback,
            )

    def set_action_active(self, action_id: str, active: bool) -> None:
        self.update_action(action_id, active=active)

    def set_action_visible(self, action_id: str, visible: bool) -> None:
        btn = self._buttons.get(action_id)
        if btn is not None:
            btn.setVisible(visible)
