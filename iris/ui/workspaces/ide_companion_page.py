"""IDE Companion — 우측 세로 레이아웃. 채팅 목록은 기본 화면과 같은 패널."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iris.ui.monitor.chat_history_panel import ChatHistoryPanel
from iris.ui.shared.theme_tokens import TOKENS

# 기본 화면 좌측 스플리터 초기 폭(main_window setSizes 220)과 같음
CHAT_LIST_WIDTH = 220

# 상단 구체 슬롯 — 좁은 20% 컬럼에서 3.0 스케일은 슬롯 밖으로 번져 로그와 겹쳤음
EMAIL_ORB_HEIGHT = 260
EMAIL_ORB_SCALE = 2.1
_UNIFIED_IDE_RATIO = 0.8


class IdeUnifiedShell(QWidget):
    """단일 창 내부 — 좌 IDE 80% + 우 Iris Companion 20% (두 창 타일 대체)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeUnifiedShell")
        # ponytail: 셸 전체 void_black이면 우측에서 사이버/구체가 안 비침 — IDE만 불투명
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent;")

        self._split = QSplitter(Qt.Orientation.Horizontal, self)
        self._split.setObjectName("IdeUnifiedHSplit")
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(6)
        self._split.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._split.setStyleSheet(
            "QSplitter#IdeUnifiedHSplit { background: transparent; }"
            "QSplitter#IdeUnifiedHSplit::handle {"
            " width: 6px; margin: 0; border: none; background: rgba(255,255,255,0.22);"
            "}"
        )

        self._ide_host = QWidget(self)
        self._ide_host.setObjectName("IdeUnifiedIdeHost")
        self._ide_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._ide_host.setStyleSheet(f"background-color: {TOKENS.void_black};")
        self._ide_host.setMinimumWidth(240)
        self._ide_lay = QVBoxLayout(self._ide_host)
        # ponytail: Companion grip 모드에선 0 — 기본은 좌/하단 8px (activity/status 여유)
        self._ide_lay.setContentsMargins(8, 0, 0, 8)
        self._ide_lay.setSpacing(0)

        self._iris_host = QWidget(self)
        self._iris_host.setObjectName("IdeUnifiedIrisHost")
        self._iris_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._iris_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._iris_host.setStyleSheet("background: transparent;")
        self._iris_host.setMinimumWidth(160)
        self._iris_lay = QVBoxLayout(self._iris_host)
        self._iris_lay.setContentsMargins(0, 0, 0, 0)
        self._iris_lay.setSpacing(0)

        self._split.addWidget(self._ide_host)
        self._split.addWidget(self._iris_host)
        self._split.setStretchFactor(0, 4)
        self._split.setStretchFactor(1, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._split)

        self._ide: QWidget | None = None
        self._companion: IdeCompanionPage | None = None
        self._on_split_changed = None
        self._user_ratio: float | None = None
        self._split.splitterMoved.connect(self._remember_split)

    def set_split_changed_callback(self, cb) -> None:
        """좌측 host 폭 변경 시 HWND 도킹 sync 등."""
        self._on_split_changed = cb

    def set_ide_insets(self, left: int, top: int, right: int, bottom: int) -> None:
        """Companion grip 숨김 시 Theia 여백 조정."""
        self._ide_lay.setContentsMargins(left, top, right, bottom)

    def mount(self, ide: QWidget | None, companion: IdeCompanionPage, *, total_w: int) -> None:
        """좌측은 HWND 도킹 placeholder(ide=None), 우측 Companion만 Qt 자식."""
        if self._ide is not None and ide is not None and self._ide is not ide:
            self._ide_lay.removeWidget(self._ide)
        if self._companion is not None and self._companion is not companion:
            self._iris_lay.removeWidget(self._companion)
        if ide is not None:
            self._ide_lay.addWidget(ide)
            ide.show()
            self._ide = ide
        else:
            self._ide = None
        self._iris_lay.addWidget(companion)
        self._companion = companion
        companion.show()
        self.apply_ratio(total_w)

    def reset_user_ratio(self) -> None:
        """컴패니언에 새로 들어갈 때만 8:2로 되돌린다."""
        self._user_ratio = None

    def split_handle_width(self) -> int:
        return int(self._split.handleWidth())

    def apply_ratio(self, total_w: int, ratio: float | None = None) -> None:
        use = self._user_ratio if ratio is None else ratio
        if use is None:
            use = _UNIFIED_IDE_RATIO
        use = min(0.88, max(0.5, float(use)))
        w = max(1, int(total_w))
        ide_w = int(w * use)
        iris_w = w - ide_w
        self._split.setSizes([ide_w, max(1, iris_w)])

    def shift_iris_width(self, delta: int) -> None:
        """채팅 목록 폭만큼 기존 스플리터 비율을 옮긴다. 드래그와 같은 기억 경로."""
        sizes = self._split.sizes()
        if len(sizes) != 2 or not delta:
            return
        total = sizes[0] + sizes[1]
        if total <= 0:
            return
        iris = sizes[1] + int(delta)
        iris = max(self._iris_host.minimumWidth(), min(total - self._ide_host.minimumWidth(), iris))
        self._split.setSizes([total - iris, iris])
        # setSizes는 splitterMoved를 안 쏘므로, 드래그가 쓰는 기억 경로를 그대로 호출
        self._remember_split()

    def _remember_split(self, *_args) -> None:
        sizes = self._split.sizes()
        total = sum(sizes)
        if total > 0:
            self._user_ratio = sizes[0] / total
        cb = self._on_split_changed
        if callable(cb):
            cb()

    def is_mounted(self) -> bool:
        return self._companion is not None

    def clear_hosts(self) -> None:
        """자식은 호출 측이 다른 레이아웃으로 옮김 — 여기선 참조만 끊음."""
        self._ide = None
        self._companion = None

    def iris_host(self) -> QWidget:
        """우측 Companion 컬럼 — Visualizer geometry 앵커용."""
        return self._iris_host

    def ide_host(self) -> QWidget:
        return self._ide_host


def _secondary_sidebar_icon(*, active: bool) -> QIcon:
    """Cursor 보조 사이드바 버튼과 같은 오른쪽 칸 아이콘."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(TOKENS.neon_cyan if active else TOKENS.text_muted)
    painter.setPen(QPen(color, 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(1, 2, 13, 12, 1.5, 1.5)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(10, 3, 3, 10)
    painter.end()
    return QIcon(pix)


class IdeCompanionPage(QWidget):
    """
    위→아래: 구체 슬롯 · Live Activity · 채팅 (이메일 우측 패널과 동일 배치).
    우측 상단 버튼으로 기본 화면과 같은 채팅 목록을 연다.
    addWidget만으로 reparent — remove/setParent(None) 금지.
    채팅 드래그가 예약 슬롯 높이를 줄여도 구체의 렌더링 위치는 유지한다.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeCompanionPage")
        # ponytail: 불투명 void_black이면 사이버 배경과 색이 갈라짐 — 이전처럼 투과
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent;")

        root = QHBoxLayout(self)
        # IDE 좌측 가장자리 그립(8px)과 겹치지 않게 우측 패널만 살짝 여백
        root.setContentsMargins(0, 6, 6, 6)
        root.setSpacing(0)

        self._column = QWidget(self)
        self._column.setObjectName("IdeCompanionColumn")
        self._column.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._column.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._column.setStyleSheet("background: transparent;")
        self._lay = QVBoxLayout(self._column)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)

        self._history_wrap = QWidget(self)
        self._history_wrap.setObjectName("IdeChatListColumn")
        self._history_wrap.setFixedWidth(CHAT_LIST_WIDTH)
        self._history_wrap.setStyleSheet(
            "QWidget#IdeChatListColumn {"
            f" border-left: 1px solid {TOKENS.panel_border};"
            " background: transparent;"
            "}"
        )
        history_lay = QVBoxLayout(self._history_wrap)
        history_lay.setContentsMargins(8, 0, 4, 0)
        history_lay.setSpacing(0)
        self._history = ChatHistoryPanel(self._history_wrap)
        history_lay.addWidget(self._history)
        self._history_wrap.hide()

        root.addWidget(self._column, 1)
        root.addWidget(self._history_wrap, 0)

        self._sidebar_btn = QToolButton(self._column)
        self._sidebar_btn.setObjectName("IdeChatListToggle")
        self._sidebar_btn.setFixedSize(28, 28)
        self._sidebar_btn.setIconSize(QSize(16, 16))
        self._sidebar_btn.setCheckable(True)
        self._sidebar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sidebar_btn.setToolTip("채팅 목록")
        self._sidebar_btn.setStyleSheet(
            """
            QToolButton#IdeChatListToggle {
                background: transparent;
                border: none;
                padding: 0;
                border-radius: 4px;
            }
            QToolButton#IdeChatListToggle:hover {
                background: rgba(37, 99, 235, 0.14);
            }
            QToolButton#IdeChatListToggle:checked {
                background: rgba(34, 211, 238, 0.12);
            }
            """
        )
        self._chat_list_open = False
        self._width_delta_cb: Callable[[int], None] | None = None
        self._sidebar_btn.clicked.connect(self._toggle_chat_list)
        self._sidebar_btn.show()
        self._sync_sidebar_icon()
        self._column.installEventFilter(self)

        self._mounted: list[QWidget] = []
        self._orb_spacer: QWidget | None = None
        self._embedded_orb: QWidget | None = None
        self._orb_height = EMAIL_ORB_HEIGHT
        # Confine the backdrop to this column; shrinking the layout spacer must
        # not resize, move or clip the orb before the chat fade reaches it.
        self._orb_host = QWidget(self)
        self._orb_host.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._orb_host.setStyleSheet("background: transparent;")
        self._orb_lay = QVBoxLayout(self._orb_host)
        self._orb_lay.setContentsMargins(0, 0, 0, 0)
        self._orb_lay.setSpacing(0)
        self._orb_host.lower()

    @property
    def chat_history(self) -> ChatHistoryPanel:
        return self._history

    @property
    def chat_list_open(self) -> bool:
        return self._chat_list_open

    def chat_list_width(self) -> int:
        return CHAT_LIST_WIDTH

    def set_width_delta_callback(self, cb: Callable[[int], None] | None) -> None:
        """목록 폭이 늘거나 줄 때 IDE/Iris 스플리터에 넘긴다."""
        self._width_delta_cb = cb

    def set_chat_list_open(self, open_: bool) -> None:
        open_ = bool(open_)
        if open_ == self._chat_list_open:
            return
        self._chat_list_open = open_
        if open_:
            self._history_wrap.show()
            delta = CHAT_LIST_WIDTH
        else:
            self._history_wrap.hide()
            delta = -CHAT_LIST_WIDTH
        self._sidebar_btn.setChecked(open_)
        self._sync_sidebar_icon()
        cb = self._width_delta_cb
        if callable(cb):
            cb(delta)
        self._place_sidebar_button()

    def _toggle_chat_list(self, _checked: bool = False) -> None:
        self.set_chat_list_open(not self._chat_list_open)

    def _sync_sidebar_icon(self) -> None:
        self._sidebar_btn.setIcon(_secondary_sidebar_icon(active=self._chat_list_open))

    def _place_sidebar_button(self) -> None:
        btn = self._sidebar_btn
        x = max(0, self._column.width() - btn.width() - 4)
        btn.move(x, 2)
        btn.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._column and event.type() == QEvent.Type.Resize:
            self._place_sidebar_button()
        return super().eventFilter(obj, event)

    def mount(
        self,
        *,
        orb_spacer: QWidget,
        live_activity: QWidget,
        chat: QWidget,
        orb_height: int = EMAIL_ORB_HEIGHT,
        activity_height: int,
    ) -> None:
        self._orb_height = orb_height
        reset = getattr(chat, "reset_height_expansion", None)
        if callable(reset):
            reset()
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
        self._orb_spacer = orb_spacer
        for w in self._mounted:
            w.show()
        self._place_sidebar_button()

    def embed_orb(self, viz: QWidget, orb_spacer: QWidget | None = None) -> None:
        """컬럼 내부 배경에 구체를 두어 채팅 확장 시 블러 경계를 통과시킨다."""
        spacer = orb_spacer or self._orb_spacer
        if spacer is None:
            return
        viz.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # addWidget → cyberspace에서 원자적 reparent (setParent(None) 금지)
        self._orb_lay.addWidget(viz, 1)
        self._sync_orb_backdrop()
        self._orb_host.show()
        self._orb_host.lower()
        viz.show()
        self._embedded_orb = viz
        self._orb_spacer = spacer
        self._place_sidebar_button()

    def _sync_orb_backdrop(self) -> None:
        margins = self._lay.contentsMargins()
        self._orb_host.setGeometry(
            margins.left(), margins.top(),
            max(0, self.width() - margins.left() - margins.right()),
            self._orb_height,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_orb_backdrop()

    def release_embedded_orb(self) -> None:
        """포인터만 해제 — Visualizer reparent는 cyberspace.set_orb_layer가 담당."""
        self._embedded_orb = None
        self._orb_host.hide()

    def embedded_orb(self) -> QWidget | None:
        return self._embedded_orb

    def transfer_to(self, target_layout: QVBoxLayout, stretches: tuple[int, int, int]) -> None:
        """companion → assistant center 로 원자적 복귀."""
        if len(self._mounted) != 3:
            return
        orb, activity, chat = self._mounted
        reset = getattr(chat, "reset_height_expansion", None)
        if callable(reset):
            reset()
        self._mounted = []
        self._orb_spacer = None
        self._embedded_orb = None
        target_layout.addWidget(orb, stretches[0])
        target_layout.addWidget(activity, stretches[1])
        target_layout.addWidget(chat, stretches[2])
        orb.show()
        activity.show()
        chat.show()

    def is_mounted(self) -> bool:
        return bool(self._mounted)
