"""캘린더 워크스페이스 — 월간 달력 + 일정 + 우측 아이리스 채팅."""

from __future__ import annotations

import calendar
import webbrowser
from datetime import date, datetime, time

from PyQt6.QtCore import QTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from iris.infrastructure.kr_holiday_client import KrHoliday
from iris.infrastructure.map_place_search import (
    MapPlace,
    google_map_url,
    kakao_map_url,
    naver_map_url,
    search_places,
)
from iris.storage.calendar_events import CalendarEvent
from iris.ui.settings.hud_dialog import (
    configure_form,
    configure_hud_dialog,
    make_form_label,
    make_hint,
    make_title,
)
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisPanel

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")

_NAV_ARROW_QSS = """
QPushButton#CalendarNavArrow {
    background: transparent;
    color: #e2e8f0;
    border: none;
    padding: 0 4px;
    font-size: 28px;
    font-weight: 300;
    min-width: 36px;
    max-width: 44px;
}
QPushButton#CalendarNavArrow:hover { color: #22d3ee; }
QPushButton#CalendarNavArrow:pressed { color: #38bdf8; }
"""

_CHIP_BTN_QSS = f"""
QPushButton {{
    background: {TOKENS.panel_overlay};
    color: {TOKENS.text_primary};
    border: 1px solid {TOKENS.border_subtle};
    border-radius: {TOKENS.radius_sm}px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    border-color: {TOKENS.accent_border};
    background: {TOKENS.panel_hover};
}}
"""


class _PlacePickerDialog(QDialog):
    """장소 검색·선택 — OSM Nominatim + 외부 지도 앱 열기."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="장소 선택",
            min_w=480,
            min_h=420,
            default_w=520,
            default_h=480,
        )
        self._selected: MapPlace | None = None
        self._results: list[MapPlace] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        root.addWidget(make_title("장소"))
        root.addWidget(make_hint("검색 후 선택하세요. 카카오·네이버·구글맵에서 확인할 수 있습니다."))

        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("장소 · 건물 · 주소 검색")
        self._query.returnPressed.connect(self._run_search)
        search_btn = QPushButton("검색")
        search_btn.clicked.connect(self._run_search)
        row.addWidget(self._query, 1)
        row.addWidget(search_btn)
        root.addLayout(row)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row)
        root.addWidget(self._list, 1)

        self._preview = QLabel("선택된 장소 없음")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(f"color: {TOKENS.text_secondary}; font-size: 12px;")
        root.addWidget(self._preview)

        map_row = QHBoxLayout()
        for label, opener in (
            ("카카오맵", self._open_kakao),
            ("네이버맵", self._open_naver),
            ("구글맵", self._open_google),
        ):
            btn = QPushButton(label)
            btn.setStyleSheet(_CHIP_BTN_QSS)
            btn.clicked.connect(opener)
            map_row.addWidget(btn)
        map_row.addStretch(1)
        root.addLayout(map_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("선택")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _run_search(self) -> None:
        self._list.clear()
        self._results = search_places(self._query.text())
        if not self._results:
            self._list.addItem("검색 결과 없음")
            self._selected = None
            self._preview.setText("선택된 장소 없음")
            return
        for place in self._results:
            self._list.addItem(place.label)

    def _on_row(self, row: int) -> None:
        if row < 0 or row >= len(self._results):
            self._selected = None
            self._preview.setText("선택된 장소 없음")
            return
        self._selected = self._results[row]
        self._preview.setText(self._selected.label)

    def _open_kakao(self) -> None:
        if self._selected:
            webbrowser.open(kakao_map_url(self._selected))

    def _open_naver(self) -> None:
        if self._selected:
            webbrowser.open(naver_map_url(self._selected))

    def _open_google(self) -> None:
        if self._selected:
            webbrowser.open(google_map_url(self._selected))

    def selected_place(self) -> MapPlace | None:
        return self._selected


class _AddEventDialog(QDialog):
    """일정 추가 — Iris HUD (일정 · 시간 · 장소 · 메모)."""

    def __init__(self, default_day: date, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="일정 추가",
            min_w=440,
            min_h=420,
            default_w=480,
            default_h=460,
        )
        self._day = default_day
        self._place: MapPlace | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)
        root.addWidget(make_title("일정 추가"))
        root.addWidget(
            make_hint(f"{default_day.year}년 {default_day.month}월 {default_day.day}일")
        )

        form = QFormLayout()
        configure_form(form)

        self._title = QLineEdit()
        self._title.setPlaceholderText("일정")
        form.addRow(make_form_label("일정"), self._title)

        self._time = QTimeEdit()
        self._time.setDisplayFormat("HH:mm")
        self._time.setTime(QTime(9, 0))
        self._time.setButtonSymbols(QTimeEdit.ButtonSymbols.UpDownArrows)
        self._time.setStyleSheet(
            f"""
            QTimeEdit {{
                background-color: {TOKENS.panel_overlay};
                color: {TOKENS.text_primary};
                border: 1px solid {TOKENS.border_subtle};
                border-radius: {TOKENS.radius_sm}px;
                padding: 7px 9px;
                min-height: 22px;
            }}
            QTimeEdit:focus {{ border: 1px solid {TOKENS.accent_border}; }}
            QTimeEdit::up-button, QTimeEdit::down-button {{
                width: 18px;
                background: transparent;
                border: none;
            }}
            """
        )
        form.addRow(make_form_label("시간"), self._time)

        place_row = QHBoxLayout()
        place_row.setSpacing(8)
        self._place_btn = QPushButton("위치 선택")
        self._place_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._place_btn.setStyleSheet(_CHIP_BTN_QSS)
        self._place_btn.clicked.connect(self._pick_place)
        self._place_clear = QPushButton("지우기")
        self._place_clear.setStyleSheet(_CHIP_BTN_QSS)
        self._place_clear.clicked.connect(self._clear_place)
        place_row.addWidget(self._place_btn, 1)
        place_row.addWidget(self._place_clear, 0)
        place_wrap = QWidget()
        place_wrap.setLayout(place_row)
        form.addRow(make_form_label("장소"), place_wrap)

        self._note = QPlainTextEdit()
        self._note.setPlaceholderText("메모")
        self._note.setMinimumHeight(90)
        form.addRow(make_form_label("메모"), self._note)

        root.addLayout(form)
        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_place(self) -> None:
        dlg = _PlacePickerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        place = dlg.selected_place()
        if place is None:
            return
        self._place = place
        self._place_btn.setText(place.name)

    def _clear_place(self) -> None:
        self._place = None
        self._place_btn.setText("위치 선택")

    def payload(self) -> tuple[str, str, str, str]:
        """title, start_at ISO, note, place label."""
        title = self._title.text().strip()
        qt = self._time.time()
        start = datetime.combine(
            self._day,
            time(qt.hour(), qt.minute(), 0),
        ).isoformat(timespec="seconds")
        note = self._note.toPlainText().strip()
        place = self._place.label if self._place else ""
        return title, start, note, place


class CalendarWorkspacePage(QWidget):
    """중앙 월간 달력/일정 + 우측 아이리스 패널."""

    calendar_chat_send = pyqtSignal(str)
    add_event_requested = pyqtSignal(str, str, str, str)  # title, start, note, place
    delete_event_requested = pyqtSignal(int)
    month_changed = pyqtSignal(int, int)
    refresh_holidays_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CalendarWorkspacePage")
        today = date.today()
        self._year = today.year
        self._month = today.month
        self._selected = today
        self._events: list[CalendarEvent] = []
        self._holidays: dict[str, list[str]] = {}
        self._holiday_status = ""
        self._day_buttons: dict[date, QPushButton] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)
        splitter.addWidget(self._build_center())

        self.iris_panel = WorkspaceIrisPanel(
            name_prefix="Calendar",
            placeholder="일정 추가·관리를 요청하세요 (예: 내일 3시 회의 잡아줘)",
        )
        self.iris_panel.setMinimumWidth(240)
        self.iris_panel.setMaximumWidth(380)
        self.iris_panel.chat_send.connect(self.calendar_chat_send.emit)
        splitter.addWidget(self.iris_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 320])
        outer.addWidget(splitter)

    def _build_center(self) -> QWidget:
        center = QWidget()
        center.setObjectName("WorkspacePanel")
        lay = QVBoxLayout(center)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self._today_btn = QPushButton("오늘")
        self._refresh_btn = QPushButton("공휴일 갱신")
        self._add_btn = QPushButton("일정 추가")
        for btn in (self._today_btn, self._refresh_btn, self._add_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_CHIP_BTN_QSS)

        self._prev = QPushButton("‹")
        self._next = QPushButton("›")
        for arrow in (self._prev, self._next):
            arrow.setObjectName("CalendarNavArrow")
            arrow.setCursor(Qt.CursorShape.PointingHandCursor)
            arrow.setStyleSheet(_NAV_ARROW_QSS)
            arrow.setFlat(True)
            arrow.setFixedHeight(40)

        self._title = QLabel()
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            "color: #e2e8f0; font-size: 26px; font-weight: 600; letter-spacing: 0.5px;"
        )

        month_block = QHBoxLayout()
        month_block.setSpacing(2)
        month_block.setContentsMargins(0, 0, 0, 0)
        month_block.addWidget(self._prev, 0, Qt.AlignmentFlag.AlignVCenter)
        month_block.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)
        month_block.addWidget(self._next, 0, Qt.AlignmentFlag.AlignVCenter)
        month_wrap = QWidget()
        month_wrap.setLayout(month_block)

        nav.addWidget(self._today_btn, 0)
        nav.addWidget(self._refresh_btn, 0)
        nav.addStretch(1)
        nav.addWidget(month_wrap, 0)
        nav.addStretch(1)
        nav.addWidget(self._add_btn, 0)
        lay.addLayout(nav)

        self._status = QLabel()
        self._status.setStyleSheet("color: #64748b; font-size: 11px;")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(2)
        for i, name in enumerate(_WEEKDAYS):
            lbl = QLabel(name)
            color = "#f87171" if i >= 5 else "#94a3b8"
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(18)
            lbl.setStyleSheet(
                f"color: {color}; font-size: 12px; font-weight: 600; padding: 0;"
            )
            self._grid.addWidget(lbl, 0, i)
            self._grid.setRowMinimumHeight(0, 18)
        lay.addWidget(self._grid_host, 1)

        day_row = QHBoxLayout()
        day_row.setSpacing(8)
        self._day_list = QListWidget()
        self._day_list.setObjectName("CalendarDayList")
        self._day_list.setStyleSheet(
            """
            QListWidget#CalendarDayList {
                background: transparent; border: 1px solid rgba(148,163,184,0.12);
                border-radius: 6px; outline: none;
            }
            QListWidget#CalendarDayList::item { padding: 6px 8px; color: #e2e8f0; }
            QListWidget#CalendarDayList::item:selected { background: rgba(56, 189, 248, 0.14); }
            """
        )
        self._day_list.setMaximumHeight(160)
        self._plus_btn = QPushButton("+")
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setFixedSize(40, 40)
        self._plus_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {TOKENS.panel_overlay};
                color: {TOKENS.neon_cyan};
                border: 1px solid {TOKENS.border_color};
                border-radius: 20px;
                font-size: 22px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {TOKENS.panel_hover};
                border-color: {TOKENS.accent_border};
            }}
            """
        )
        day_row.addWidget(self._day_list, 1)
        day_row.addWidget(
            self._plus_btn,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        lay.addLayout(day_row)

        self._prev.clicked.connect(self._on_prev)
        self._next.clicked.connect(self._on_next)
        self._today_btn.clicked.connect(self._on_today)
        self._add_btn.clicked.connect(self._on_add)
        self._plus_btn.clicked.connect(self._on_add)
        self._refresh_btn.clicked.connect(self.refresh_holidays_requested.emit)
        self._day_list.itemDoubleClicked.connect(self._on_delete_item)

        self._rebuild_grid()
        self._refresh_day_list()
        return center

    @property
    def year(self) -> int:
        return self._year

    @property
    def month(self) -> int:
        return self._month

    @property
    def selected_day(self) -> date:
        return self._selected

    def set_events(self, events: list[CalendarEvent]) -> None:
        self._events = list(events)
        self._rebuild_grid()
        self._refresh_day_list()

    def set_holidays(self, holidays: list[KrHoliday], status: str = "") -> None:
        self._holidays = {}
        for h in holidays:
            self._holidays.setdefault(h.date, []).append(h.name)
        self._holiday_status = status
        self._status.setText(status)
        self._rebuild_grid()
        self._refresh_day_list()

    def _on_prev(self) -> None:
        if self._month == 1:
            self._year -= 1
            self._month = 12
        else:
            self._month -= 1
        self._rebuild_grid()
        self.month_changed.emit(self._year, self._month)

    def _on_next(self) -> None:
        if self._month == 12:
            self._year += 1
            self._month = 1
        else:
            self._month += 1
        self._rebuild_grid()
        self.month_changed.emit(self._year, self._month)

    def _on_today(self) -> None:
        today = date.today()
        self._year, self._month = today.year, today.month
        self._selected = today
        self._rebuild_grid()
        self._refresh_day_list()
        self.month_changed.emit(self._year, self._month)

    def _on_add(self) -> None:
        dlg = _AddEventDialog(self._selected, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title, start, note, place = dlg.payload()
        if title and start:
            self.add_event_requested.emit(title, start, note, place)

    def _on_delete_item(self, item: QListWidgetItem) -> None:
        eid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(eid, int) and eid > 0:
            self.delete_event_requested.emit(eid)

    def _events_for_day(self, day: date) -> list[CalendarEvent]:
        key = day.isoformat()
        out: list[CalendarEvent] = []
        for ev in self._events:
            try:
                dt = datetime.fromisoformat(ev.start_at)
            except ValueError:
                continue
            if dt.date().isoformat() == key:
                out.append(ev)
        return out

    def _rebuild_grid(self) -> None:
        self._title.setText(f"{self._year}년 {self._month}월")
        for btn in self._day_buttons.values():
            self._grid.removeWidget(btn)
            btn.deleteLater()
        self._day_buttons.clear()

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(self._year, self._month)
        today = date.today()
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                btn = QPushButton()
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(52)
                in_month = day.month == self._month
                holidays = self._holidays.get(day.isoformat(), [])
                day_events = self._events_for_day(day) if in_month else []
                lines = [str(day.day)]
                if holidays:
                    lines.append(holidays[0][:6])
                elif day_events:
                    lines.append(day_events[0].title[:6])
                btn.setText("\n".join(lines))
                selected = day == self._selected
                is_hol = bool(holidays)
                fg = "#64748b"
                if in_month:
                    fg = "#f87171" if (c >= 5 or is_hol) else "#e2e8f0"
                bg = "transparent"
                border = "1px solid rgba(148,163,184,0.10)"
                if day == today and in_month:
                    border = "1px solid rgba(56, 189, 248, 0.55)"
                if selected and in_month:
                    bg = "rgba(56, 189, 248, 0.14)"
                if day_events and in_month:
                    border = "1px solid rgba(94, 234, 212, 0.35)"
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: {bg};
                        color: {fg};
                        border: {border};
                        border-radius: 6px;
                        text-align: left;
                        padding: 4px 6px;
                        font-size: 12px;
                    }}
                    QPushButton:hover {{ background: rgba(148, 163, 184, 0.08); }}
                    """
                )
                btn.setEnabled(in_month)
                if in_month:
                    btn.clicked.connect(lambda _=False, d=day: self._select_day(d))
                self._grid.addWidget(btn, r, c)
                self._day_buttons[day] = btn

    def _select_day(self, day: date) -> None:
        self._selected = day
        self._rebuild_grid()
        self._refresh_day_list()

    def select_day_iso(self, day_iso: str) -> date:
        """MCP/외부 — 'YYYY-MM-DD' 선택. 연월이 다르면 월도 이동."""
        day = date.fromisoformat((day_iso or "").strip())
        if day.year != self._year or day.month != self._month:
            self._year, self._month = day.year, day.month
            self.month_changed.emit(self._year, self._month)
        self._select_day(day)
        return day

    def set_month(self, year: int, month: int) -> None:
        self._year = int(year)
        self._month = int(month)
        if self._month < 1 or self._month > 12:
            raise ValueError("month must be 1..12")
        self._rebuild_grid()
        self.month_changed.emit(self._year, self._month)

    def _refresh_day_list(self) -> None:
        self._day_list.clear()
        holidays = self._holidays.get(self._selected.isoformat(), [])
        for name in holidays:
            item = QListWidgetItem(f"공휴일 · {name}")
            item.setData(Qt.ItemDataRole.UserRole, 0)
            self._day_list.addItem(item)
        for ev in self._events_for_day(self._selected):
            try:
                t = datetime.fromisoformat(ev.start_at).strftime("%H:%M")
            except ValueError:
                t = ""
            label = f"{t}  {ev.title}" if t and not ev.all_day else ev.title
            if ev.place:
                label += f"  ·  {ev.place.split('—')[0].strip()}"
            if ev.note:
                label += f" — {ev.note}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ev.id)
            item.setToolTip("더블클릭하면 삭제")
            self._day_list.addItem(item)
