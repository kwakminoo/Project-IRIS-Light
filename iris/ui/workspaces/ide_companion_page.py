"""IDE Companion — 우측 20% 전용 세로 레이아웃 (사이드바 없음)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from iris.ui.shared.theme_tokens import TOKENS

# 상단 구체 슬롯 — 좁은 20% 컬럼에서 3.0 스케일은 슬롯 밖으로 번져 로그와 겹쳤음
EMAIL_ORB_HEIGHT = 260
EMAIL_ORB_SCALE = 2.1


class IdeCompanionPage(QWidget):
    """
    위→아래: 구체 슬롯 · Live Activity · 채팅 (이메일 우측 패널과 동일 배치).
    addWidget만으로 reparent — remove/setParent(None) 금지.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeCompanionPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {TOKENS.void_black};")
        self._lay = QVBoxLayout(self)
        # ponytail: companion은 IDE와 왼쪽이 맞닿음 — 좌측 여백 없음
        self._lay.setContentsMargins(0, 6, 6, 6)
        self._lay.setSpacing(6)
        self._mounted: list[QWidget] = []

    def mount(
        self,
        *,
        orb_spacer: QWidget,
        live_activity: QWidget,
        chat: QWidget,
        orb_height: int = EMAIL_ORB_HEIGHT,
        activity_height: int,
    ) -> None:
        orb_spacer.setMinimumHeight(orb_height)
        orb_spacer.setMaximumHeight(orb_height)
        orb_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        live_activity.setMinimumHeight(activity_height)
        live_activity.setMaximumHeight(activity_height)
        live_activity.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # addWidget이 이전 레이아웃에서 원자적으로 옮김 (orphan 창 없음)
        self._lay.addWidget(orb_spacer, 0)
        self._lay.addWidget(live_activity, 0)
        self._lay.addWidget(chat, 1)
        self._mounted = [orb_spacer, live_activity, chat]
        for w in self._mounted:
            w.show()

    def transfer_to(self, target_layout: QVBoxLayout, stretches: tuple[int, int, int]) -> None:
        """companion → assistant center 로 원자적 복귀."""
        if len(self._mounted) != 3:
            return
        orb, activity, chat = self._mounted
        self._mounted = []
        target_layout.addWidget(orb, stretches[0])
        target_layout.addWidget(activity, stretches[1])
        target_layout.addWidget(chat, stretches[2])
        orb.show()
        activity.show()
        chat.show()

    def is_mounted(self) -> bool:
        return bool(self._mounted)
