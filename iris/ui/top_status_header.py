"""상단 Status Header — 모델·상태·TTS·백엔드 연결."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from iris.assistant.external_agent_adapter import external_backend_status_line
from iris.config.settings import Settings
from iris.core.state_machine import AppState
from iris.ui.theme_tokens import TOKENS

# DragTab 상태 2행 블록 높이 — 타이틀 텍스트·칩 행 정렬 기준
STATUS_BLOCK_HEIGHT = 36
_DOT_BOX = 8
_DOT_FONT_PX = 8


def _status_dot_color(kind: str) -> str:
    """연결·상태 색상."""
    if kind in ("connected", "ready", "idle"):
        return TOKENS.success
    if kind in ("waiting", "processing", "listening", "responding"):
        return TOKENS.neon_cyan
    if kind in ("unavailable", "error"):
        return TOKENS.warning if kind == "unavailable" else TOKENS.error
    return TOKENS.text_muted


class _StatusChip(QWidget):
    """작은 색상 점 + 라벨."""

    def __init__(
        self,
        prefix: str,
        *,
        parent: QWidget | None = None,
        mono_value: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(STATUS_BLOCK_HEIGHT // 2)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(TOKENS.spacing_xs)

        self._dot = QLabel("●")
        self._dot.setObjectName("StatusDot")
        self._dot.setFixedSize(_DOT_BOX, _DOT_BOX)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_dot_color(_status_dot_color("idle"))
        row.addWidget(self._dot)

        self._prefix = QLabel(prefix.upper())
        self._prefix.setObjectName("StatusChipPrefix")
        row.addWidget(self._prefix)

        self._value = QLabel("-")
        self._value.setObjectName("StatusChipValueMono" if mono_value else "StatusChipValue")
        row.addWidget(self._value)

    def _apply_dot_color(self, color: str) -> None:
        self._dot.setStyleSheet(
            f"color: {color}; font-size: {_DOT_FONT_PX}px;"
            " background: transparent; border: none; padding: 0; margin: 0;"
        )

    def set_value(self, text: str, *, dot_kind: str = "idle") -> None:
        self._value.setText(text)
        self._apply_dot_color(_status_dot_color(dot_kind))


class TopStatusHeader:
    """DragTab에 삽입할 상태 칩 묶음 — 3열 그리드로 dot 세로 정렬."""

    def __init__(self) -> None:
        self._status_block = QWidget()
        self._status_block.setObjectName("TopStatusBlock")
        self._status_block.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._status_block.setFixedHeight(STATUS_BLOCK_HEIGHT)

        grid = QGridLayout(self._status_block)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(TOKENS.spacing_md)
        grid.setVerticalSpacing(0)

        self._state_chip = _StatusChip("STATE")
        self._model_chip = _StatusChip("MODEL", mono_value=True)
        self._tts_chip = _StatusChip("TTS")
        self._local_chip = _StatusChip("IRIS LOCAL")
        self._openclaw_chip = _StatusChip("OPENCLAW")
        self._hermes_chip = _StatusChip("HERMES")

        cell_align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        grid.addWidget(self._state_chip, 0, 0, alignment=cell_align)
        grid.addWidget(self._model_chip, 0, 1, alignment=cell_align)
        grid.addWidget(self._tts_chip, 0, 2, alignment=cell_align)
        grid.addWidget(self._local_chip, 1, 0, alignment=cell_align)
        grid.addWidget(self._openclaw_chip, 1, 1, alignment=cell_align)
        grid.addWidget(self._hermes_chip, 1, 2, alignment=cell_align)

        self._state_chip.set_value("IDLE", dot_kind="idle")
        self._model_chip.set_value("-", dot_kind="idle")

        # StatusStrip 호환 — MainWindow가 참조하는 라벨
        self.model_label = self._model_chip._value  # noqa: SLF001
        self.status_label = self._state_chip._value  # noqa: SLF001
        self.tts_status_label = self._tts_chip._value  # noqa: SLF001

        self._local_chip.set_value("CONNECTED", dot_kind="connected")

        # place_status_rows 레거시 — 그리드에 backend가 포함되어 빈 슬롯만 제공
        self._empty_legacy = QWidget()
        self._empty_legacy.setFixedHeight(0)
        self._empty_legacy.hide()

    def status_widget(self) -> QWidget:
        """DragTab — STATE/MODEL/TTS + 백엔드 3열 그리드."""
        return self._status_block

    def primary_row(self) -> QWidget:
        """레거시 호환 — status_widget()과 동일."""
        return self._status_block

    def backend_row(self) -> QWidget:
        """레거시 호환 — 그리드에 포함되어 빈 위젯 반환."""
        return self._empty_legacy

    def set_app_state(self, state: AppState) -> None:
        name = state.name
        kind = "idle"
        if state in (AppState.LISTENING,):
            kind = "listening"
        elif state in (AppState.PROCESSING, AppState.EXECUTING):
            kind = "processing"
        elif state in (AppState.RESPONDING,):
            kind = "responding"
        elif state in (AppState.ERROR, AppState.ALERTING):
            kind = "error"
        self._state_chip.set_value(name, dot_kind=kind)

    def set_model_name(self, name: str) -> None:
        display = name.strip() if name.strip() else "(unset)"
        self._model_chip.set_value(display, dot_kind="connected")

    def set_tts_status(self, text: str) -> None:
        lower = text.lower()
        kind = "ready"
        if "error" in lower or "fail" in lower:
            kind = "error"
        elif "busy" in lower or "speak" in lower:
            kind = "processing"
        self._tts_chip.set_value(text.upper(), dot_kind=kind)

    def refresh_backend_status(self, settings: Settings | None) -> None:
        """OpenClaw/Hermes 가용성 갱신."""
        line = external_backend_status_line(settings)
        oc = "UNAVAILABLE"
        hm = "UNAVAILABLE"
        if "OpenClaw (Connected)" in line:
            oc = "CONNECTED"
        if "Hermes (Connected)" in line:
            hm = "CONNECTED"
        self._openclaw_chip.set_value(
            oc,
            dot_kind="connected" if oc == "CONNECTED" else "unavailable",
        )
        self._hermes_chip.set_value(
            hm,
            dot_kind="connected" if hm == "CONNECTED" else "unavailable",
        )
