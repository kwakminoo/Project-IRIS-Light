"""채팅 패널."""

from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QGuiApplication, QImage, QPalette, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.core.activity_privacy import prepare_chat_text
from iris.ui.chat_display import (
    TYPING_CHARS_PER_TICK,
    TYPING_INTERVAL_MS,
    TYPING_SPEECH_MAX_CHARS_PER_TICK,
    chat_body_to_html,
    effective_typing_duration_ms,
    extend_typing_timeline_ms,
    markdown_to_chat_html,
    normalize_chat_body,
    scale_typing_duration_ms,
    typing_body_to_html,
    typing_target_index,
    visible_typing_text,
)
from iris.ui.composer_plus_menu import ComposerPlusButton, ComposerPlusMenu, ComposerSendButton
from iris.ui.context_ring import ContextRingWidget
from iris.ui.mic_waveform_bar import MicWaveformBar

if TYPE_CHECKING:
    from iris.infrastructure.ollama_client import OllamaModelInfo


_IMAGE_FILTER = (
    "Images & Videos (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp4 *.webm *.mov);;"
    "All Files (*.*)"
)
_FILE_FILTER = "All Files (*.*)"


def _paste_dir() -> Path:
    d = Path.home() / ".iris-light" / "paste"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_clipboard_image(image: QImage) -> str | None:
    if image.isNull():
        return None
    name = f"paste_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.png"
    path = _paste_dir() / name
    try:
        if image.save(str(path), "PNG"):
            return str(path.resolve())
    except OSError:
        return None
    return None


def _paths_from_mime(mime) -> list[str]:
    if mime is None:
        return []
    out: list[str] = []
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile():
                p = url.toLocalFile().strip()
                if p:
                    out.append(p)
    return out


def _paths_from_clipboard() -> list[str]:
    """클립보드의 파일 URL 또는 이미지를 로컬 경로 목록으로."""
    cb = QGuiApplication.clipboard()
    if cb is None:
        return []
    mime = cb.mimeData()
    paths = _paths_from_mime(mime)
    if paths:
        return paths
    img = cb.image()
    if not img.isNull():
        saved = _save_clipboard_image(img)
        return [saved] if saved else []
    if mime is not None and mime.hasImage():
        data = mime.imageData()
        if isinstance(data, QImage) and not data.isNull():
            saved = _save_clipboard_image(data)
            return [saved] if saved else []
    return []


def _mime_has_attachable(mime) -> bool:
    if mime is None:
        return False
    if mime.hasUrls():
        return any(u.isLocalFile() for u in mime.urls())
    return bool(mime.hasImage())


class ChatComposerInput(QLineEdit):
    """텍스트 + 클립보드 이미지 붙여넣기 + 파일 드래그앤드롭."""

    files_attached = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def paste(self) -> None:
        paths = _paths_from_clipboard()
        if paths:
            self.files_attached.emit(paths)
            return
        super().paste()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        paths = _paths_from_mime(mime)
        if not paths and mime is not None and mime.hasImage():
            data = mime.imageData()
            if isinstance(data, QImage) and not data.isNull():
                saved = _save_clipboard_image(data)
                if saved:
                    paths = [saved]
        if paths:
            self.files_attached.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class _ChatInputBar(QWidget):
    """입력칸 안쪽: + | 입력 | 모델 | 전송."""

    files_attached = pyqtSignal(list)  # list[str] paths
    skill_inserted = pyqtSignal(str)
    mcp_inserted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatInputBar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            """
            QWidget#ChatInputBar {
                background: transparent;
                border: none;
            }
            """
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 6, 4)
        row.setSpacing(0)

        self._input_shell = QWidget()
        self._input_shell.setObjectName("ChatInputShell")
        self._input_shell.setAcceptDrops(True)
        self._input_shell.setStyleSheet(
            """
            QWidget#ChatInputShell {
                background: transparent;
                border: none;
            }
            """
        )
        shell_row = QHBoxLayout(self._input_shell)
        shell_row.setContentsMargins(6, 2, 4, 2)
        shell_row.setSpacing(6)

        self.plus_button = ComposerPlusButton()
        self._plus_menu = ComposerPlusMenu(self)
        self.plus_button.clicked.connect(self._toggle_plus_menu)
        self._plus_menu.add_photos.connect(self._pick_photos)
        self._plus_menu.add_files.connect(self._pick_files)
        self._plus_menu.skill_chosen.connect(self._on_skill)
        self._plus_menu.mcp_chosen.connect(self._on_mcp)

        self.input = ChatComposerInput()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Iris에게 메시지를 입력하세요…")
        self.input.setStyleSheet(
            """
            QLineEdit {
                background: transparent;
                color: #ffffff;
                border: none;
                padding: 4px 0;
            }
            """
        )
        self.input.files_attached.connect(self._on_paths_attached)

        self.model_combo = QComboBox()
        self.model_combo.setObjectName("ChatModelCombo")
        self.model_combo.setToolTip("Ollama 모델 선택")
        self.model_combo.setMinimumWidth(120)
        self.model_combo.setMaximumWidth(240)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_combo.addItem("(모델 불러오는 중…)", "")
        self.model_combo.setStyleSheet(
            """
            QComboBox#ChatModelCombo {
                background: transparent;
                color: #e2e8f0;
                border: none;
                padding: 2px 4px;
                font-size: 11px;
                min-height: 22px;
            }
            QComboBox#ChatModelCombo::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox#ChatModelCombo QAbstractItemView {
                background-color: #0f172a;
                color: #e2e8f0;
                selection-background-color: #1e3a5f;
                border: 1px solid rgba(56, 189, 248, 0.28);
            }
            """
        )

        self.context_ring = ContextRingWidget()

        self._model_shell = QWidget()
        self._model_shell.setObjectName("ChatModelShell")
        self._model_shell.setStyleSheet(
            """
            QWidget#ChatModelShell {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 8px;
            }
            """
        )
        model_row = QHBoxLayout(self._model_shell)
        model_row.setContentsMargins(6, 2, 4, 2)
        model_row.setSpacing(4)
        model_row.addWidget(self.context_ring, 0, Qt.AlignmentFlag.AlignVCenter)
        model_row.addWidget(self.model_combo, 1, Qt.AlignmentFlag.AlignVCenter)

        self.send_button = ComposerSendButton()

        shell_row.addWidget(self.plus_button, 0, Qt.AlignmentFlag.AlignVCenter)
        shell_row.addWidget(self.input, 1)
        shell_row.addWidget(self._model_shell, 0, Qt.AlignmentFlag.AlignVCenter)
        shell_row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._input_shell, 1)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        paths = _paths_from_mime(mime)
        if not paths and mime is not None and mime.hasImage():
            data = mime.imageData()
            if isinstance(data, QImage) and not data.isNull():
                saved = _save_clipboard_image(data)
                if saved:
                    paths = [saved]
        if paths:
            self._on_paths_attached(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _toggle_plus_menu(self) -> None:
        if self._plus_menu.isVisible():
            self._plus_menu.hide()
            return
        # 열 때마다 스킬/MCP 목록 갱신
        self._plus_menu.deleteLater()
        self._plus_menu = ComposerPlusMenu(self)
        self._plus_menu.add_photos.connect(self._pick_photos)
        self._plus_menu.add_files.connect(self._pick_files)
        self._plus_menu.skill_chosen.connect(self._on_skill)
        self._plus_menu.mcp_chosen.connect(self._on_mcp)
        self._plus_menu.popup_above(self.plus_button)

    def _pick_photos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Photos & Videos",
            "",
            _IMAGE_FILTER,
        )
        if paths:
            self._on_paths_attached(paths)

    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Files",
            "",
            _FILE_FILTER,
        )
        if paths:
            self._on_paths_attached(paths)

    def _on_paths_attached(self, paths: list[str]) -> None:
        clean = [str(p).strip() for p in paths if str(p).strip()]
        if not clean:
            return
        self._insert_paths(clean)
        self.files_attached.emit(clean)

    def _insert_paths(self, paths: list[str]) -> None:
        bits = " ".join(f'"{p}"' for p in paths)
        cur = self.input.text()
        sep = "" if not cur or cur.endswith(" ") else " "
        self.input.setText(cur + sep + bits)
        self.input.setFocus()

    def _on_skill(self, name: str) -> None:
        token = f"/{name} "
        cur = self.input.text()
        sep = "" if not cur or cur.endswith(" ") else " "
        self.input.setText(cur + sep + token)
        self.input.setFocus()
        self.skill_inserted.emit(name)

    def _on_mcp(self, name: str) -> None:
        token = f"@mcp:{name} "
        cur = self.input.text()
        sep = "" if not cur or cur.endswith(" ") else " "
        self.input.setText(cur + sep + token)
        self.input.setFocus()
        self.mcp_inserted.emit(name)


class _ChatInputArea(QWidget):
    """입력칸 + 하단 마이크 주파수 바."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatInputArea")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            """
            QWidget#ChatInputArea {
                background: transparent;
                border: none;
            }
            """
        )
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.input_bar = _ChatInputBar()
        self.waveform = MicWaveformBar()
        self.waveform.setStyleSheet(
            """
            MicWaveformBar {
                background: transparent;
                border: none;
            }
            """
        )

        col.addWidget(self.input_bar)
        col.addWidget(self.waveform)

        # 리사이즈 시 출력창이 입력 영역 높이를 침범하지 않도록 고정
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self.input_bar.sizeHint().height() + self.waveform.minimumHeight())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _mime_has_attachable(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        paths = _paths_from_mime(mime)
        if not paths and mime is not None and mime.hasImage():
            data = mime.imageData()
            if isinstance(data, QImage) and not data.isNull():
                saved = _save_clipboard_image(data)
                if saved:
                    paths = [saved]
        if paths:
            self.input_bar._on_paths_attached(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class ChatPanel(QWidget):
    send_clicked = pyqtSignal(str)
    model_changed = pyqtSignal(str)
    files_attached = pyqtSignal(list)
    skill_inserted = pyqtSignal(str)
    mcp_inserted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChatPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._log = QTextEdit()
        self._log.setObjectName("ChatLog")
        self._log.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._log.setReadOnly(True)
        self._log.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        # 스크롤바는 숨기고 마우스 휠로만 스크롤
        self._log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent = QColor(0, 0, 0, 0)
        log_pal = self._log.palette()
        log_pal.setColor(QPalette.ColorRole.Base, transparent)
        log_pal.setColor(QPalette.ColorRole.Window, transparent)
        self._log.setPalette(log_pal)
        self._log.setMinimumHeight(80)
        self._log.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._log.setStyleSheet(
            """
            QTextEdit#ChatLog {
                background: transparent;
                border: none;
                padding: 8px 4px;
            }
            """
        )
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        self._typing_timer.timeout.connect(self._type_next_chunk)
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = False
        self._typing_speech_duration_ms: float | None = None
        self._typing_speech_start: float | None = None
        self._stream_active = False
        self._stream_who = "Iris"
        self._stream_block_start: int | None = None
        self._typing_body_start: int | None = None
        self._typing_render_markdown = False
        self._user_listening_active = False
        self._input_area = _ChatInputArea()
        self._input = self._input_area.input_bar.input
        self._model_combo = self._input_area.input_bar.model_combo
        self._context_ring = self._input_area.input_bar.context_ring
        self._waveform = self._input_area.waveform
        self._context_limit = 128_000
        self._context_used = 0
        self._input.returnPressed.connect(self._emit_send)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_area.input_bar.send_button.clicked.connect(self._emit_send)
        self._model_combo.currentIndexChanged.connect(self._on_model_index_changed)
        bar = self._input_area.input_bar
        bar.files_attached.connect(self.files_attached.emit)
        bar.skill_inserted.connect(self.skill_inserted.emit)
        bar.mcp_inserted.connect(self.mcp_inserted.emit)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addWidget(self._log, 1)
        root.addWidget(self._input_area, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(self._log.minimumHeight() + self._input_area.minimumHeight() + 8)

    @property
    def waveform(self) -> MicWaveformBar:
        """하단 마이크 파형 바 (기동 연출 등)."""
        return self._waveform

    def current_model(self) -> str:
        data = self._model_combo.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip()
        return self._model_combo.currentText().strip()

    def set_models(
        self,
        models: list["OllamaModelInfo"] | list[str],
        *,
        selected: str = "",
    ) -> None:
        """Ollama 모델 목록으로 콤보 갱신 (표시=catalog, 값=runtime)."""
        from iris.infrastructure.ollama_client import OllamaModelInfo, display_name_from_runtime

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if not models:
            self._model_combo.addItem("(모델 없음 — Ollama 확인)", "")
            self._model_combo.blockSignals(False)
            return

        entries: list[tuple[str, str]] = []
        for item in models:
            if isinstance(item, OllamaModelInfo):
                entries.append((item.catalog_name or display_name_from_runtime(item.name), item.name))
            else:
                runtime = str(item).strip()
                if runtime:
                    entries.append((display_name_from_runtime(runtime), runtime))

        from iris.infrastructure.model_descriptions import describe_model

        for i, (label, runtime) in enumerate(entries):
            self._model_combo.addItem(label, runtime)
            desc = describe_model(runtime)
            if desc:
                self._model_combo.setItemData(i, desc, Qt.ItemDataRole.ToolTipRole)

        pick = selected.strip()
        idx = 0
        if pick:
            for i, (label, runtime) in enumerate(entries):
                if pick in (runtime, label):
                    idx = i
                    break
        self._model_combo.setCurrentIndex(idx)
        self._model_combo.blockSignals(False)
        self._update_model_tooltip()
        self.model_changed.emit(self.current_model())

    def set_model_status(self, text: str) -> None:
        """목록 로드 실패 등 상태 문구."""
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(text, "")
        self._model_combo.blockSignals(False)

    def set_context_usage(self, used: int, limit: int) -> None:
        """모델 선택 박스 안 원형 컨텍스트 게이지 갱신."""
        self._context_used = max(0, int(used))
        self._context_limit = max(1, int(limit))
        self._context_ring.set_usage(self._context_used, self._context_limit)

    def _update_model_tooltip(self) -> None:
        """콤보 툴팁을 현재 선택 모델의 설명으로 갱신(없으면 기본 안내)."""
        from iris.infrastructure.model_descriptions import describe_model

        desc = describe_model(self.current_model())
        self._model_combo.setToolTip(desc or "Ollama 모델 선택")

    def _on_model_index_changed(self, _index: int) -> None:
        self._update_model_tooltip()
        self.model_changed.emit(self.current_model())

    def _scroll_log_to_bottom(self, *, deferred: bool = False) -> None:
        """새 메시지·음성 인식 결과가 항상 보이도록 출력창을 맨 아래로 스크롤."""

        def _do_scroll() -> None:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)
            self._log.ensureCursorVisible()
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())

        if deferred:
            QTimer.singleShot(0, _do_scroll)
        else:
            _do_scroll()

    def set_mic_level(self, level: float) -> None:
        """상시 듣기 마이크 레벨 — 하단 주파수 바에 반영."""
        self._waveform.set_level(level)

    def set_speech_threshold_rms(self, speech_rms: float) -> None:
        """인식 감도 임계 — 점선 위치 갱신."""
        self._waveform.set_threshold_rms(speech_rms)

    def begin_user_listening(self) -> None:
        """발화 시작 — 플레이스홀더로 즉시 피드백."""
        self.finish_typing()
        self._remove_user_listening_line()
        self._log.append("<b>나</b>: <i style='color:#94a3b8'>…</i>")
        self._user_listening_active = True
        self._scroll_log_to_bottom(deferred=True)

    def set_user_listening_status(self, status: str) -> None:
        """STT 진행 등 상태 문구 갱신."""
        if not self._user_listening_active:
            self.begin_user_listening()
        self._remove_user_listening_line()
        safe = html.escape(status)
        self._log.append(f"<b>나</b>: <i style='color:#94a3b8'>{safe}</i>")
        self._user_listening_active = True
        self._scroll_log_to_bottom(deferred=True)

    def cancel_user_listening(self) -> None:
        """인식 취소·게이트 거부 시 플레이스홀더 제거."""
        if self._user_listening_active:
            self._remove_user_listening_line()
        self._user_listening_active = False

    def complete_user_message_typed(self, text: str) -> None:
        """음성 인식 완료 — 플레이스홀더 제거 후 본문 즉시 표시."""
        self.cancel_user_listening()
        self.append_message_instant("나", text)

    @property
    def typing_buffer_text(self) -> str:
        """버퍼·스트림 중 누적 본문 (TTS 동기화용)."""
        return self._typing_text

    def append_message(self, who: str, text: str) -> None:
        """Iris 등 — 타이핑 효과로 출력 (TTS 동기화 없음)."""
        self.append_message_typed(who, text, speech_sync=False)

    def _begin_chat_message_cursor(self) -> QTextCursor:
        """새 메시지 블록을 문서 끝·좌측 정렬로 시작.

        직전 Iris 마크다운(<ul>/<li>)이 남긴 list/indent를 끊지 않으면
        다음 You/Iris 줄이 들여쓰기된 채 이어진다.
        """
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextBlockFormat()
        fmt.setIndent(0)
        fmt.setTextIndent(0.0)
        fmt.setLeftMargin(0.0)
        if self._log.toPlainText().strip():
            cursor.insertBlock(fmt)
        else:
            cursor.setBlockFormat(fmt)
        lst = cursor.currentList()
        if lst is not None:
            lst.remove(cursor.block())
            cursor.setBlockFormat(fmt)
        return cursor

    def append_message_instant(self, who: str, text: str) -> None:
        """사용자 입력 등 — 타이핑 없이 본문 전체를 즉시 표시."""
        self.finish_typing()
        body = normalize_chat_body(who, prepare_chat_text(text))
        if not body:
            return
        cursor = self._begin_chat_message_cursor()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        if who.strip().lower() == "iris":
            cursor.insertHtml(markdown_to_chat_html(body))
        else:
            cursor.insertHtml(chat_body_to_html(body))
        self._log.setTextCursor(cursor)
        self._scroll_log_to_bottom()

    def begin_stream_message(self, who: str, *, speech_sync: bool = True) -> None:
        """LLM 스트리밍 — speech_sync면 TTS와 동기 타이핑, 아니면 청크 즉시 표시."""
        self.finish_typing()
        self._stream_active = True
        self._stream_who = who
        cursor = self._begin_chat_message_cursor()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._stream_block_start = cursor.position()
        self._typing_body_start = cursor.position()
        self._typing_render_markdown = who.strip().lower() == "iris"
        self._log.setTextCursor(cursor)
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = speech_sync
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        self._typing_timer.stop()
        self._scroll_log_to_bottom()

    def append_stream_chunk(self, text: str) -> None:
        """스트리밍 청크 — speech_sync면 버퍼만, 아니면 누적 본문을 즉시 표시."""
        text = prepare_chat_text(text)
        if not text:
            return
        if not self._stream_active:
            self.begin_stream_message("Iris", speech_sync=self._typing_speech_sync)
        self._append_typing_buffer(text)
        if not self._typing_speech_sync:
            self._typing_index = len(self._typing_text)
            self._replace_typing_body()
            self._scroll_log_to_bottom()

    def end_stream_message(self, final_text: str | None = None) -> None:
        """스트림 종료 — 정규화 본문으로 버퍼 확정 (화면 재삽입 없음)."""
        if final_text is not None:
            final_text = prepare_chat_text(final_text)
        if not self._stream_active:
            if final_text:
                self.append_message("Iris", final_text)
            return
        who = getattr(self, "_stream_who", "Iris")
        if final_text is not None:
            self._finalize_typing_buffer(who, final_text)
        self._stream_active = False
        self._stream_block_start = None
        self._ensure_buffered_typing_fallback()
        if not self._typing_speech_sync:
            self.finish_typing()
        self._scroll_log_to_bottom(deferred=True)

    def append_message_typed(
        self,
        who: str,
        text: str,
        *,
        speech_sync: bool = False,
    ) -> None:
        """한 글자씩 표시. Iris + speech_sync면 TTS 재생 시작 후 sync_typing_to_speech 호출."""
        self.finish_typing()
        body = normalize_chat_body(who, prepare_chat_text(text))
        cursor = self._begin_chat_message_cursor()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        self._typing_body_start = cursor.position()
        self._typing_render_markdown = who.strip().lower() == "iris"
        self._log.setTextCursor(cursor)
        self._typing_text = body
        self._typing_index = 0
        self._typing_speech_sync = speech_sync
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        if speech_sync:
            self._typing_timer.stop()
        else:
            self._typing_timer.setInterval(TYPING_INTERVAL_MS)
            self._typing_timer.start()
        self._scroll_log_to_bottom()

    def sync_typing_to_speech(
        self,
        duration_ms: float,
        *,
        visible_len: int | None = None,
        spoken_len: int | None = None,
    ) -> None:
        """TTS 재생 길이에 맞춰 대기 중인 본문 타이핑을 시작한다."""
        if not self._typing_text or not self._typing_speech_sync:
            return
        text_len = visible_len if visible_len is not None else len(self._typing_text)
        if spoken_len is not None and spoken_len > 0:
            scaled = scale_typing_duration_ms(duration_ms, text_len, spoken_len)
        else:
            scaled = float(duration_ms)
        self._typing_speech_duration_ms = effective_typing_duration_ms(
            len(self._typing_text),
            scaled,
        )
        self._typing_speech_start = None
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        if not self._typing_timer.isActive():
            self._typing_timer.start()

    def extend_typing_for_speech_segment(
        self,
        spoken: str,
        duration_ms: float,
    ) -> None:
        """후속 TTS 세그먼트 — 타이핑 타임라인 예산을 이어서 확장."""
        if not self._typing_text or not self._typing_speech_sync:
            return
        remaining = len(self._typing_text) - self._typing_index
        if remaining <= 0:
            return
        spoken_len = max(len((spoken or "").strip()), 1)
        scaled = scale_typing_duration_ms(duration_ms, remaining, spoken_len)
        if self._typing_speech_start is None:
            self.sync_typing_to_speech(
                duration_ms,
                visible_len=remaining,
                spoken_len=spoken_len,
            )
            return
        elapsed_ms = (time.monotonic() - self._typing_speech_start) * 1000.0
        self._typing_speech_duration_ms = extend_typing_timeline_ms(
            elapsed_ms,
            remaining,
            scaled,
        )

    def on_speech_typing_finished(self, *, flush: bool = True) -> None:
        """TTS 종료·중단 시 남은 글자를 즉시 표시 (다구간 TTS는 flush=False)."""
        if flush and self._typing_speech_sync:
            self.finish_typing()

    def finish_typing(self) -> None:
        """진행 중인 타이핑 효과를 즉시 완료한다."""
        if not self._typing_timer.isActive() and not self._typing_text:
            return
        self._typing_timer.stop()
        if self._typing_render_markdown and self._typing_body_start is not None:
            self._render_markdown_body()
        elif self._typing_index < len(self._typing_text):
            self._typing_index = len(self._typing_text)
            self._replace_typing_body()
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = False
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        self._typing_body_start = None
        self._typing_render_markdown = False
        self._scroll_log_to_bottom()

    def _remove_user_listening_line(self) -> None:
        """마지막 '나: …' 플레이스홀더 블록 제거."""
        plain = self._log.toPlainText()
        if not plain.strip():
            return
        lines = plain.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].startswith("나:"):
            lines.pop()
        self._log.setPlainText("\n".join(lines))
        if lines:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)
            self._scroll_log_to_bottom()

    def _append_typing_buffer(self, chunk: str) -> None:
        """타이핑 버퍼만 확장 — 스트리밍 중 화면에는 아직 표시하지 않음."""
        if not chunk:
            return
        old_len = len(self._typing_text)
        self._typing_text += chunk
        if (
            self._typing_speech_sync
            and self._typing_speech_duration_ms
            and self._typing_speech_start is not None
            and old_len > 0
        ):
            new_len = len(self._typing_text)
            if new_len > old_len:
                self._typing_speech_duration_ms *= new_len / old_len

    def _finalize_typing_buffer(self, who: str, final_text: str) -> None:
        """스트림 종료 시 정규화 본문으로 버퍼 확정."""
        body = normalize_chat_body(who, prepare_chat_text(final_text))
        old = self._typing_text
        self._typing_text = body
        if self._typing_index > len(body):
            self._typing_index = len(body)
        if self._typing_speech_sync and self._typing_speech_duration_ms and old:
            self._typing_speech_duration_ms *= len(body) / max(len(old), 1)

    def _ensure_buffered_typing_fallback(self) -> None:
        """TTS가 시작되지 않은 스트림 — 일반 타이핑으로 폴백."""
        if (
            not self._typing_text
            or not self._typing_speech_sync
            or self._typing_speech_duration_ms is not None
            or self._typing_timer.isActive()
        ):
            return
        self._typing_speech_sync = False
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        self._typing_timer.start()

    def _replace_typing_body(self) -> None:
        """타이핑 본문 영역을 현재 인덱스까지의 평문으로 갱신."""
        if self._typing_body_start is None:
            return
        visible = visible_typing_text(
            self._typing_text,
            self._typing_index,
            render_markdown=self._typing_render_markdown,
        )
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        cursor.movePosition(
            QTextCursor.MoveOperation.End,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        if visible:
            cursor.insertHtml(typing_body_to_html(visible))
        self._log.setTextCursor(cursor)

    def _render_markdown_body(self) -> None:
        """타이핑 완료 후 마크다운 원문을 렌더링된 HTML로 교체."""
        if self._typing_body_start is None or not self._typing_text:
            return
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(markdown_to_chat_html(self._typing_text))
        self._log.setTextCursor(cursor)

    def _type_next_chunk(self) -> None:
        if self._typing_index >= len(self._typing_text):
            self._typing_timer.stop()
            if self._typing_render_markdown and self._typing_body_start is not None:
                self._render_markdown_body()
            self._typing_text = ""
            self._typing_index = 0
            self._typing_speech_sync = False
            self._typing_speech_duration_ms = None
            self._typing_speech_start = None
            self._typing_body_start = None
            self._typing_render_markdown = False
            return

        if self._typing_speech_sync and self._typing_speech_duration_ms:
            if self._typing_speech_start is None:
                self._typing_speech_start = time.monotonic()
            elapsed_ms = (time.monotonic() - self._typing_speech_start) * 1000.0
            target_index = typing_target_index(
                len(self._typing_text),
                elapsed_ms,
                self._typing_speech_duration_ms,
            )
            if target_index <= self._typing_index:
                return
            # TTS 타임라인을 따르되 한 틱에 너무 많이 점프하지 않게 제한
            self._typing_index = min(
                target_index,
                self._typing_index + TYPING_SPEECH_MAX_CHARS_PER_TICK,
            )
        else:
            self._typing_index = min(
                len(self._typing_text),
                self._typing_index + TYPING_CHARS_PER_TICK,
            )

        self._replace_typing_body()
        self._scroll_log_to_bottom()

    def _on_input_changed(self, text: str) -> None:
        self._input_area.input_bar.send_button.setEnabled(bool(text.strip()))

    def _emit_send(self) -> None:
        t = self._input.text().strip()
        if not t:
            return
        self._input.clear()
        self.send_clicked.emit(t)
