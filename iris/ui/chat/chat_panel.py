"""채팅 패널."""

from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 모델 콤보 아이템 메타 (addItem UserRole = runtime name)
_ROLE_SUPPORTS_TOOLS = int(Qt.ItemDataRole.UserRole) + 1
_ROLE_REQUIRES_SUB = int(Qt.ItemDataRole.UserRole) + 2
_ROLE_PROVIDER_NAME = int(Qt.ItemDataRole.UserRole) + 3
_COLOR_MODEL_DEFAULT = QColor("#38bdf8")  # 도구 지원·일반 선택 가능 — 밝은 푸른색
_COLOR_MODEL_NO_TOOLS = QColor("#9ca3af")  # 도구 미지원 — 회색
_COLOR_MODEL_PRO = QColor("#fca5a5")  # Pro/구독 — 옅은 붉은색

from iris.core.activity_privacy import prepare_chat_text
from iris.core.chat_citations import iris_message_to_chat_html
from iris.ui.chat.chat_image_view import (
    attach_image_loader,
    handle_chat_anchor_click,
    prefetch_chat_html_images,
)
from iris.ui.chat.chat_display import (
    TYPING_CHARS_PER_TICK,
    TYPING_INTERVAL_MS,
    TYPING_SPEECH_MAX_CHARS_PER_TICK,
    TYPING_SPEECH_MIN_CHARS_PER_SEC,
    chat_body_to_html,
    effective_typing_duration_ms,
    extend_typing_timeline_ms,
    normalize_chat_body,
    scale_typing_duration_ms,
    typing_body_to_html,
    typing_target_index,
    visible_typing_text,
)
from iris.ui.chat.composer_plus_menu import ComposerPlusButton, ComposerPlusMenu, ComposerSendButton
from iris.ui.chat.model_picker_menu import (
    ModelBrandDialog,
    ModelPickerMenu,
    PickerModel,
    split_picker_groups,
)
from iris.ui.chat.skill_mcp_dialogs import McpDialog, SkillsDialog
from iris.ui.settings.hud_dialog import run_hud_confirm
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.widgets.context_ring import ContextRingWidget
from iris.ui.widgets.mic_waveform_bar import MicWaveformBar

if TYPE_CHECKING:
    from iris.infrastructure.ollama_client import OllamaModelInfo


class _ModelCombo(QComboBox):
    """네이티브 드롭다운 대신 Iris 모델 피커 팝업을 연다."""

    popup_requested = pyqtSignal()

    def showPopup(self) -> None:  # noqa: N802
        self.popup_requested.emit()

    def show_native_popup(self) -> None:
        super().showPopup()


_IMAGE_FILTER = (
    "Images & Videos (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp4 *.webm *.mov);;"
    "All Files (*.*)"
)
_FILE_FILTER = "All Files (*.*)"
_DEFAULT_INPUT_PLACEHOLDER = "Iris에게 메시지를 입력하세요…"
# 입력창 placeholder — 푸른색 유지하되 흐릿하게
_PLACEHOLDER_COLOR = QColor(56, 189, 248, 110)  # neon_blue @ ~43%


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


class ChatComposerInput(QPlainTextEdit):
    """멀티라인 입력 — 줄바꿈 시 세로 확장, Enter=전송, Shift+Enter=개행 (Cursor 스타일)."""

    files_attached = pyqtSignal(list)
    submit_requested = pyqtSignal()

    _MIN_LINES = 1
    _MAX_LINES = 8
    _ICON_PX = 28  # ComposerPlusButton / SendButton 와 동일

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTabChangesFocus(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDocumentMargin(2)
        self._adjusting_height = False
        self.document().contentsChanged.connect(self._adjust_height)
        self._adjust_height()

    # QLineEdit 호환 — 기존 호출부 유지
    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:  # noqa: N802
        self.setPlainText(text or "")
        self._adjust_height()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear(self) -> None:
        super().clear()
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                self._adjust_height()
                return
            # Enter alone → send (Cursor composer)
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _line_height(self) -> int:
        fm = self.fontMetrics()
        return max(fm.height(), fm.lineSpacing())

    def _content_height_px(self) -> int:
        # ponytail: QPlainTextDocumentLayout.size().height()는 픽셀이 아니라 줄 수.
        # 픽셀 높이는 blockBoundingRect 합산이 정답. (천장: 줄 wrap/개행 레이아웃)
        doc = self.document()
        layout = doc.documentLayout()
        if layout is None:
            return self._line_height()
        doc.setTextWidth(max(1, self.viewport().width()))
        total = 0.0
        block = doc.firstBlock()
        while block.isValid():
            total += layout.blockBoundingRect(block).height()
            block = block.next()
        total += 2.0 * float(doc.documentMargin())
        return max(self._line_height(), int(total + 0.5))

    def _adjust_height(self) -> None:
        if self._adjusting_height:
            return
        self._adjusting_height = True
        try:
            line_h = self._line_height()
            doc_h = self._content_height_px()
            # 스타일시트 padding 등 viewport 바깥 여백
            chrome = (
                max(0, self.height() - self.viewport().height())
                if self.viewport().height() > 0
                else 0
            )
            max_h = (
                line_h * self._MAX_LINES
                + int(2 * self.document().documentMargin())
                + 4
                + chrome
            )
            # 한 줄: 아이콘(28px)과 동일 높이 — 같은 가로선
            if doc_h <= line_h + 2:
                new_h = max(self._ICON_PX, line_h + chrome)
            else:
                new_h = max(self._ICON_PX, min(doc_h + 4 + chrome, max_h))
            if self.height() != new_h:
                self.setFixedHeight(new_h)
            self.updateGeometry()
            # 입력 셸 → 바 → 입력 영역까지 레이아웃 무효화 (위로 확장)
            w = self.parentWidget()
            while w is not None:
                w.updateGeometry()
                if w.objectName() == "ChatInputArea" and hasattr(w, "sync_height_to_contents"):
                    w.sync_height_to_contents()
                    break
                w = w.parentWidget()
        finally:
            self._adjusting_height = False

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(super().sizeHint().width(), max(self._ICON_PX, self.height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(60, self._ICON_PX)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.viewport() is not None:
            self.viewport().setAutoFillBackground(False)
            self.viewport().setStyleSheet("background: transparent; border: none;")
        self._adjust_height()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adjust_height()

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


class ChatLogTextEdit(QTextEdit):
    speaker_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        attach_image_loader(self)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        anchor = self.anchorAt(event.pos())
        if anchor.startswith("iris-tts://"):
            self.speaker_clicked.emit(anchor.removeprefix("iris-tts://"))
            event.accept()
            return
        if anchor.startswith("iris-stt://"):
            event.accept()
            return
        if handle_chat_anchor_click(self, anchor):
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ChatMicButton(QPushButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatMicButton")
        self.setText("🎤")
        self.setToolTip("마이크 녹음 시작/정지")
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setStyleSheet(
            """
            QPushButton#ChatMicButton {
                background-color: rgba(15, 23, 42, 0.85);
                color: #e2e8f0;
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 14px;
                padding: 0;
            }
            QPushButton#ChatMicButton:checked {
                background-color: rgba(127, 29, 29, 0.95);
                border-color: rgba(248, 113, 113, 0.55);
            }
            """
        )


class _ChatInputBar(QWidget):
    """입력칸 — + · 텍스트 · 모델 · 전송을 한 줄(투명 셸) 안에 배치."""

    files_attached = pyqtSignal(list)  # list[str] paths
    skill_inserted = pyqtSignal(str)
    mcp_inserted = pyqtSignal(str)
    mic_clicked = pyqtSignal()

    _ICON_PX = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatInputBar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        self._input_shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._input_shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._input_shell.setStyleSheet(
            """
            QWidget#ChatInputShell {
                background: transparent;
                border: none;
            }
            """
        )
        shell_row = QHBoxLayout(self._input_shell)
        shell_row.setContentsMargins(8, 0, 8, 0)
        shell_row.setSpacing(8)

        self.plus_button = ComposerPlusButton()
        self._plus_menu = ComposerPlusMenu(self)
        self.plus_button.clicked.connect(self._toggle_plus_menu)
        self._wire_plus_menu(self._plus_menu)

        self.input = ChatComposerInput()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText(_DEFAULT_INPUT_PLACEHOLDER)
        self.input.setStyleSheet(
            """
            QPlainTextEdit#ChatInput {
                background: transparent;
                color: #ffffff;
                border: none;
                padding: 0px;
            }
            """
        )
        _ph = self.input.palette()
        _ph.setColor(QPalette.ColorRole.PlaceholderText, _PLACEHOLDER_COLOR)
        self.input.setPalette(_ph)
        self.input.files_attached.connect(self._on_paths_attached)

        self.model_combo = _ModelCombo()
        self.model_combo.setObjectName("ChatModelCombo")
        self.model_combo.setToolTip("Ollama 모델 선택")
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_combo.setEditable(False)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.addItem("(모델 불러오는 중…)", "")
        self.model_combo.setStyleSheet(
            """
            QComboBox#ChatModelCombo {
                background: transparent;
                color: #ffffff;
                border: none;
                padding: 2px 14px 2px 0px;
                font-size: 11px;
                min-height: 22px;
                text-align: left;
            }
            QComboBox#ChatModelCombo::drop-down {
                border: none;
                background: transparent;
                width: 12px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }
            QComboBox#ChatModelCombo::down-arrow {
                width: 8px;
                height: 8px;
            }
            QComboBox#ChatModelCombo QAbstractItemView {
                background-color: rgba(56, 120, 168, 0.55);
                border: none;
                border-top: 1px solid rgba(56, 189, 248, 0.95);
                border-bottom: 1px solid rgba(56, 189, 248, 0.95);
                outline: none;
                padding: 4px 0;
            }
            QComboBox#ChatModelCombo QAbstractItemView::item {
                /* 색은 ForegroundRole(도구/Pro 구분) — 스타일시트 고정색 금지 */
                padding: 6px 10px;
                min-height: 22px;
                background: transparent;
            }
            QComboBox#ChatModelCombo QAbstractItemView::item:selected {
                color: #ffffff;
                background-color: rgba(56, 189, 248, 0.22);
            }
            QComboBox#ChatModelCombo QAbstractItemView::item:hover {
                background-color: rgba(56, 189, 248, 0.14);
            }
            """
        )
        _view = self.model_combo.view()
        if _view is not None:
            pal = _view.palette()
            pal.setColor(QPalette.ColorRole.Text, QColor("#94a3b8"))
            pal.setColor(QPalette.ColorRole.Base, QColor(56, 120, 168, 140))
            pal.setColor(QPalette.ColorRole.Highlight, QColor(56, 189, 248, 56))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            _view.setPalette(pal)
            _view.setFrameShape(QFrame.Shape.NoFrame)

        self.context_ring = ContextRingWidget()
        self.context_ring.setCursor(Qt.CursorShape.PointingHandCursor)
        self.context_ring.setToolTip("컨텍스트 사용량 — 클릭 시 모델 목록")

        # 게이지 + 모델명이 한 덩어리: [●][모델명 ▼] — 폭은 내용에 맞춤
        self._model_shell = QWidget()
        self._model_shell.setObjectName("ChatModelShell")
        self._model_shell.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_shell.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._model_shell.setStyleSheet(
            """
            QWidget#ChatModelShell {
                background: transparent;
                border: none;
                border-radius: 0px;
            }
            """
        )
        model_row = QHBoxLayout(self._model_shell)
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(4)
        model_row.addWidget(self.context_ring, 0, Qt.AlignmentFlag.AlignVCenter)
        model_row.addWidget(self.model_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._model_shell.installEventFilter(self)
        self.context_ring.installEventFilter(self)

        self.send_button = ComposerSendButton()

        self._right_cluster = QWidget()
        self._right_cluster.setObjectName("ChatInputRightCluster")
        self._right_cluster.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._right_cluster.setStyleSheet(
            "QWidget#ChatInputRightCluster { background: transparent; border: none; }"
        )
        right_row = QHBoxLayout(self._right_cluster)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(2)
        right_row.addWidget(self._model_shell, 0, Qt.AlignmentFlag.AlignVCenter)
        right_row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)

        # + · 텍스트 · (게이지+모델+전송) — 입력 확장 시 버튼은 하단 고정(Cursor/GPT)
        _bottom = Qt.AlignmentFlag.AlignBottom
        shell_row.addWidget(self.plus_button, 0, _bottom)
        shell_row.addWidget(self.input, 1, _bottom)
        shell_row.addWidget(self._right_cluster, 0, _bottom)
        row.addWidget(self._input_shell, 1)
        self.fit_model_picker()
        QTimer.singleShot(0, self.fit_model_picker)

    def fit_model_picker(self) -> None:
        """선택 텍스트 + 게이지 + 화살표에 맞게 모델 박스 폭을 줄이거나 늘린다."""
        text = self.model_combo.currentText() or ""
        fm = self.model_combo.fontMetrics()
        # boundingRect가 horizontalAdvance보다 실제 글리프 폭에 가깝다
        text_w = int(fm.boundingRect(text).width())
        # drop-down(~14) + 좌우 여유 — 끝 글자 잘림 방지
        combo_w = max(32, min(300, text_w + 28))
        self.model_combo.setFixedWidth(combo_w)
        ring_w = max(self.context_ring.width(), 18)
        shell_w = ring_w + 4 + combo_w
        self._model_shell.setFixedSize(QSize(shell_w, self._ICON_PX))
        self._model_shell.updateGeometry()
        self._right_cluster.adjustSize()
        self._right_cluster.updateGeometry()
        self._input_shell.updateGeometry()
        self.updateGeometry()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        # 게이지/셸 클릭도 모델 목록 열기 (콤보 텍스트 영역은 기본 showPopup)
        if event.type() == QEvent.Type.MouseButtonPress and watched in (
            self._model_shell,
            self.context_ring,
        ):
            if self.model_combo.view() is not None and self.model_combo.view().isVisible():
                self.model_combo.hidePopup()
            else:
                self.model_combo.showPopup()
            return True
        return super().eventFilter(watched, event)

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

    def _wire_plus_menu(self, menu: ComposerPlusMenu) -> None:
        menu.add_photos.connect(self._pick_photos)
        menu.add_files.connect(self._pick_files)
        menu.skill_chosen.connect(self._on_skill)
        menu.mcp_chosen.connect(self._on_mcp)
        menu.open_skills_panel.connect(self._open_skills_dialog)
        menu.open_mcp_panel.connect(self._open_mcp_dialog)

    def _toggle_plus_menu(self) -> None:
        if self._plus_menu.isVisible():
            self._plus_menu.hide()
            return
        # 열 때마다 스킬/MCP 개수 갱신
        self._plus_menu.deleteLater()
        self._plus_menu = ComposerPlusMenu(self)
        self._wire_plus_menu(self._plus_menu)
        self._plus_menu.popup_above(self.plus_button)

    def _open_skills_dialog(self) -> None:
        # Popup 포커스 해제 후 다이얼로그 (한 틱 지연)
        QTimer.singleShot(0, self._show_skills_dialog)

    def _show_skills_dialog(self) -> None:
        dlg = SkillsDialog(self.window())
        dlg.skill_chosen.connect(self._on_skill)
        dlg.exec()

    def _open_mcp_dialog(self) -> None:
        QTimer.singleShot(0, self._show_mcp_dialog)

    def _show_mcp_dialog(self) -> None:
        dlg = McpDialog(self.window())
        dlg.mcp_chosen.connect(self._on_mcp)
        dlg.exec()

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

        # Fixed: 입력 줄 수에 따라 높이만 바뀌고, 로그가 남는 세로 공간을 먹음
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sync_height_to_contents()

    def sync_height_to_contents(self) -> None:
        # ponytail: input_bar.height()는 레이아웃이 늘린 값일 수 있어 쓰면 안 됨.
        # 입력 위젯 실측 + 바 마진(상하 4) + 파형 min.
        inp_h = max(self.input_bar.input.height(), self.input_bar.input.sizeHint().height())
        bar_h = inp_h + 8
        need = bar_h + self.waveform.minimumHeight()
        if self.height() != need or self.minimumHeight() != need:
            self.setFixedHeight(need)
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        inp_h = max(self.input_bar.input.height(), self.input_bar.input.sizeHint().height())
        return QSize(200, inp_h + 8 + self.waveform.minimumHeight())

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
    stop_clicked = pyqtSignal()
    model_changed = pyqtSignal(str)
    files_attached = pyqtSignal(list)
    skill_inserted = pyqtSignal(str)
    mcp_inserted = pyqtSignal(str)
    mic_clicked = pyqtSignal()
    speaker_clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChatPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._generating = False
        self._log = ChatLogTextEdit()
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
        # 첫 글자(Iris의 I, 한글 자모 가로획)가 좌측 가장자리에서 잘리지 않게
        # 문서 자체 여백도 확보한다. HTML inline 앞부분은 stylesheet padding만으로는
        # 플랫폼별 클리핑이 남을 수 있다.
        self._log.document().setDocumentMargin(8.0)
        self._log.document().setDefaultFont(self.font())
        self._log.setMinimumHeight(80)
        self._log.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._log.setStyleSheet(
            f"""
            QTextEdit#ChatLog {{
                background: transparent;
                border: none;
                color: {TOKENS.text_primary};
                padding: 8px 10px;
            }}
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
        self._typing_anchor_y: int | None = None
        # ponytail: speech_sync=True인데도 TTS 재생 시작 타이밍까지 타이핑이 자동으로 시작되면
        # "TTS 완성 후 텍스트 표시" 요구사항이 깨진다.
        self._typing_wait_for_tts_completion = False
        self._user_listening_active = False
        self._stt_pending = False
        self._tts_texts: dict[str, str] = {}
        self._tts_seq = 0
        self._last_tts_id = ""
        self._input_area = _ChatInputArea()
        self._input = self._input_area.input_bar.input
        self._model_combo = self._input_area.input_bar.model_combo
        self._context_ring = self._input_area.input_bar.context_ring
        self._waveform = self._input_area.waveform
        self._context_limit = 128_000
        self._context_used = 0
        self._model_guard_prev_index = 0
        self._model_guard_silent = False
        self._picker_models: list[PickerModel] = []
        self._model_picker_menu: ModelPickerMenu | None = None
        self._input.submit_requested.connect(self._on_submit_or_stop)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_area.input_bar.send_button.clicked.connect(self._on_submit_or_stop)
        self._model_combo.currentIndexChanged.connect(self._on_model_index_changed)
        self._model_combo.popup_requested.connect(self._open_model_picker_menu)
        bar = self._input_area.input_bar
        bar.files_attached.connect(self.files_attached.emit)
        bar.skill_inserted.connect(self.skill_inserted.emit)
        bar.mcp_inserted.connect(self.mcp_inserted.emit)
        self._log.speaker_clicked.connect(self.speaker_clicked.emit)

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
        """런타임 모델 id. 상태 문구(빈 data)는 모델명이 아니다."""
        data = self._model_combo.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip()
        # ponytail: set_model_status가 라벨만 바꿀 때 text를 모델로 쓰면
        # Hermes X-Hermes-Model 헤더가 latin-1로 터진다. data 없으면 미선택.
        return ""

    def current_input_text(self) -> str:
        return self._input.text()

    def set_input_text(self, text: str) -> None:
        self._input.setText(text)
        self._input.setFocus()

    def insert_input_text(self, text: str, *, separator: str = " ") -> None:
        extra = (text or "").strip()
        if not extra:
            return
        cur = self._input.text().rstrip()
        if cur:
            self._input.setText(f"{cur}{separator}{extra}")
        else:
            self._input.setText(extra)
        self._input.setFocus()

    def submit_input(self) -> None:
        """입력창 텍스트를 그대로 전송 (STT 자동전송용)."""
        self._emit_send()

    def register_tts_message(self, text: str) -> str:
        """답변별 TTS용 메시지 id 등록."""
        body = (text or "").strip()
        self._tts_seq += 1
        msg_id = f"m{self._tts_seq}"
        self._tts_texts[msg_id] = body
        self._last_tts_id = msg_id
        return msg_id

    def get_tts_text(self, token: str) -> str:
        key = (token or "").strip()
        if key in ("", "last"):
            key = self._last_tts_id
        return self._tts_texts.get(key, "")

    def set_speaker_status(self, msg_id: str, status: str) -> None:
        """답변 TTS 링크 상태(이모지 없이 텍스트만)."""
        labels = {
            "idle": "[재생]",
            "busy": "[생성중]",
            "playing": "[재생중]",
            "error": "[오류]",
        }
        label = labels.get(status, "[재생]")
        target = (msg_id or "").strip() or self._last_tts_id
        if not target:
            return
        html_doc = self._log.toHtml()
        needle = f'href="iris-tts://{target}"'
        if needle not in html_doc:
            return
        import re

        updated = re.sub(
            rf'(<a href="iris-tts://{re.escape(target)}"[^>]*>)[^<]*(</a>)',
            rf"\g<1>{label}\g<2>",
            html_doc,
            count=1,
        )
        if updated != html_doc:
            bar = self._log.verticalScrollBar()
            pos = bar.value()
            self._log.setHtml(updated)
            bar.setValue(pos)

    def _speaker_link_html(self, msg_id: str) -> str:
        return (
            f' <a href="iris-tts://{html.escape(msg_id)}" '
            f'style="color:#7dd3fc;text-decoration:none;">[재생]</a>'
        )

    def set_mic_recording(self, recording: bool) -> None:
        self._waveform.set_listening(recording)

    def set_models(
        self,
        models: list["OllamaModelInfo"] | list[str],
        *,
        selected: str = "",
    ) -> None:
        """Ollama 모델 목록으로 콤보 갱신 (표시=catalog, 값=runtime)."""
        from iris.infrastructure.ollama_client import OllamaModelInfo, display_name_from_runtime

        self._model_guard_silent = True
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if not models:
            self._picker_models = []
            self._model_combo.addItem("(모델 없음 — Ollama 확인)", "")
            self._model_combo.blockSignals(False)
            self._model_guard_silent = False
            self._model_guard_prev_index = 0
            return

        from iris.infrastructure.model_descriptions import describe_model
        from iris.storage.api_providers import is_api_runtime_model

        # label, runtime, supports_tools, requires_subscription, provider_name
        entries: list[tuple[str, str, bool, bool, str]] = []
        for item in models:
            if isinstance(item, OllamaModelInfo):
                label = item.catalog_name or display_name_from_runtime(item.name)
                provider = ""
                if is_api_runtime_model(item.name) and " · " in label:
                    provider = label.split(" · ", 1)[0].strip()
                entries.append(
                    (
                        label,
                        item.name,
                        bool(item.supports_tools),
                        bool(item.requires_subscription),
                        provider,
                    )
                )
            else:
                runtime = str(item).strip()
                if runtime:
                    entries.append((display_name_from_runtime(runtime), runtime, True, False, ""))

        self._picker_models = []
        for i, (label, runtime, supports_tools, requires_sub, provider) in enumerate(entries):
            self._model_combo.addItem(label, runtime)
            self._model_combo.setItemData(i, supports_tools, _ROLE_SUPPORTS_TOOLS)
            self._model_combo.setItemData(i, requires_sub, _ROLE_REQUIRES_SUB)
            self._model_combo.setItemData(i, provider, _ROLE_PROVIDER_NAME)
            color = _COLOR_MODEL_DEFAULT
            tip_extra = ""
            if requires_sub:
                color = _COLOR_MODEL_PRO
                tip_extra = " (Pro/구독 전용)"
            elif not supports_tools:
                color = _COLOR_MODEL_NO_TOOLS
                tip_extra = " (도구 호출 미지원)"
            self._model_combo.setItemData(i, QBrush(color), Qt.ItemDataRole.ForegroundRole)
            if is_api_runtime_model(runtime):
                from iris.infrastructure.api_model_meta import card_blurb, describe_api_model
                from iris.storage.api_providers import parse_runtime_model_id

                parsed = parse_runtime_model_id(runtime)
                mid = parsed[1] if parsed else runtime
                tip = card_blurb(describe_api_model(provider or "API", mid)) + tip_extra
            else:
                desc = describe_model(runtime)
                tip = (desc or runtime) + tip_extra
            self._model_combo.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)
            self._picker_models.append(
                PickerModel(
                    runtime=runtime,
                    label=label,
                    supports_tools=supports_tools,
                    requires_subscription=requires_sub,
                    provider_name=provider,
                    is_api=is_api_runtime_model(runtime),
                )
            )

        pick = selected.strip()
        idx = 0
        if pick:
            for i, (label, runtime, _t, _s, _p) in enumerate(entries):
                if pick in (runtime, label):
                    idx = i
                    break
        self._model_combo.setCurrentIndex(idx)
        self._model_guard_prev_index = idx
        self._model_combo.blockSignals(False)
        self._model_guard_silent = False
        self._update_model_tooltip()
        self._input_area.input_bar.fit_model_picker()
        self.model_changed.emit(self.current_model())

    def set_model_status(self, text: str) -> None:
        """목록 로드 중/실패 상태 문구. 기존 런타임 id는 data에 유지."""
        prev = ""
        data = self._model_combo.currentData()
        if isinstance(data, str) and data.strip():
            prev = data.strip()
        self._model_guard_silent = True
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._picker_models = []
        self._model_combo.addItem(text, prev)
        self._model_combo.blockSignals(False)
        self._model_guard_silent = False
        self._model_guard_prev_index = 0
        self._input_area.input_bar.fit_model_picker()

    def set_context_usage(self, used: int, limit: int) -> None:
        """모델 선택 박스 안 원형 컨텍스트 게이지 갱신."""
        self._context_used = max(0, int(used))
        self._context_limit = max(1, int(limit))
        self._context_ring.set_usage(self._context_used, self._context_limit)

    def _update_model_tooltip(self) -> None:
        """콤보 툴팁을 현재 선택 모델의 설명으로 갱신(없으면 기본 안내)."""
        from iris.infrastructure.api_model_meta import card_blurb, describe_api_model
        from iris.infrastructure.model_descriptions import describe_model
        from iris.storage.api_providers import is_api_runtime_model, parse_runtime_model_id

        runtime = self.current_model()
        if is_api_runtime_model(runtime):
            idx = self._model_combo.currentIndex()
            provider = str(self._model_combo.itemData(idx, _ROLE_PROVIDER_NAME) or "API")
            parsed = parse_runtime_model_id(runtime)
            mid = parsed[1] if parsed else runtime
            self._model_combo.setToolTip(card_blurb(describe_api_model(provider, mid)))
            return
        desc = describe_model(runtime)
        self._model_combo.setToolTip(desc or "모델 선택")

    def _confirm_special_model(self, *, requires_sub: bool, supports_tools: bool) -> bool:
        """Pro/도구미지원 선택 시 Iris HUD 안내. True면 선택 확정."""
        if requires_sub:
            return run_hud_confirm(
                self,
                title="유료 모델",
                badge="PRO",
                accent=_COLOR_MODEL_PRO.name(),
                body="이 모델은 Pro/구독 전용 유료 모델입니다.",
                hint="구독이 없으면 호출에 실패할 수 있습니다. 그래도 선택하시겠습니까?",
                ok_text="선택",
                cancel_text="취소",
            )
        if not supports_tools:
            return run_hud_confirm(
                self,
                title="도구 호출 미지원",
                badge="NO TOOLS",
                accent=TOKENS.text_muted,
                body="이 모델은 도구 호출을 지원하지 않습니다.",
                hint=(
                    "에이전트 사용(웹검색·스킬·MCP 등)에 어려움이 있을 수 있습니다. "
                    "그래도 선택하시겠습니까?"
                ),
                ok_text="선택",
                cancel_text="취소",
            )
        return True

    def _open_model_picker_menu(self) -> None:
        """+ 메뉴와 동일한 팝업 — Ollama/NVIDIA › + 단일 모델."""
        if self._model_picker_menu is not None:
            self._model_picker_menu.hide()
            self._model_picker_menu.deleteLater()
            self._model_picker_menu = None
        ollama, nvidia, multi, singles = split_picker_groups(self._picker_models)
        nvidia_label = ""
        if nvidia:
            nvidia_label = next((m.provider_name for m in nvidia if m.provider_name), "NVIDIA")
        multi_brands = []
        for pid, items in multi.items():
            name = next((m.provider_name for m in items if m.provider_name), pid)
            multi_brands.append((pid, name))
        menu = ModelPickerMenu(
            has_ollama=bool(ollama),
            nvidia_label=nvidia_label,
            multi_brands=multi_brands,
            singles=singles,
            parent=self,
        )
        menu.open_ollama.connect(
            lambda: QTimer.singleShot(0, lambda: self._show_brand_dialog("Ollama", ollama, False))
        )
        menu.open_nvidia.connect(
            lambda: QTimer.singleShot(
                0, lambda: self._show_brand_dialog(nvidia_label or "NVIDIA", nvidia, True)
            )
        )
        menu.open_brand.connect(self._on_open_multi_brand)
        menu.model_chosen.connect(self._select_model_runtime)
        self._model_picker_menu = menu
        menu.popup_above(self._input_area.input_bar._model_shell)

    def _on_open_multi_brand(self, brand_id: str) -> None:
        _ollama, _nvidia, multi, _singles = split_picker_groups(self._picker_models)
        items = multi.get(brand_id) or []
        title = next((m.provider_name for m in items if m.provider_name), brand_id)
        QTimer.singleShot(0, lambda: self._show_brand_dialog(title, items, False))

    def _show_brand_dialog(self, title: str, models: list[PickerModel], categorize: bool) -> None:
        dlg = ModelBrandDialog(
            title,
            models,
            self.window(),
            categorize=categorize,
            hint=(
                "무료 Public API 엔드포인트에서 호출 가능한 NIM만 표시합니다. "
                "시안=도구 가능 · 회색=도구 미지원(Hermes 부적합) · 붉음=유료/구독. "
                "특징·장단점·한도는 카드에 요약되어 있습니다."
                if categorize
                else "시안=도구 가능 · 회색=도구 미지원 · 붉음=유료/구독. "
                "모델을 고른 뒤 「사용」을 누르세요."
            ),
        )
        dlg.model_chosen.connect(self._select_model_runtime)
        dlg.exec()

    def _select_model_runtime(self, runtime: str) -> None:
        rt = (runtime or "").strip()
        if not rt:
            return
        for i in range(self._model_combo.count()):
            if self._model_combo.itemData(i) == rt:
                self._model_combo.setCurrentIndex(i)
                return

    def _on_model_index_changed(self, index: int) -> None:
        if self._model_guard_silent:
            return
        requires_sub = bool(self._model_combo.itemData(index, _ROLE_REQUIRES_SUB))
        supports_tools = self._model_combo.itemData(index, _ROLE_SUPPORTS_TOOLS)
        if supports_tools is None:
            supports_tools = True
        else:
            supports_tools = bool(supports_tools)

        needs_confirm = requires_sub or not supports_tools
        if needs_confirm:
            prev = self._model_guard_prev_index
            # 확인 전에는 이전 선택 유지
            self._model_guard_silent = True
            self._model_combo.blockSignals(True)
            self._model_combo.setCurrentIndex(prev)
            self._model_combo.blockSignals(False)
            self._model_guard_silent = False
            if not self._confirm_special_model(
                requires_sub=requires_sub, supports_tools=supports_tools
            ):
                return
            self._model_guard_silent = True
            self._model_combo.blockSignals(True)
            self._model_combo.setCurrentIndex(index)
            self._model_combo.blockSignals(False)
            self._model_guard_silent = False

        self._model_guard_prev_index = self._model_combo.currentIndex()
        self._update_model_tooltip()
        self._input_area.input_bar.fit_model_picker()
        self.model_changed.emit(self.current_model())

    def _scroll_log_to_bottom(self, *, deferred: bool = False) -> None:
        """새 메시지·음성 인식 결과가 항상 보이도록 출력창을 맨 아래로 스크롤.

        타이핑 앵커가 잡혀 있으면 맨 아래 대신 답변 시작 줄에서 멈춘다.
        """

        def _do_scroll() -> None:
            bar = self._log.verticalScrollBar()
            if self._typing_anchor_y is not None:
                # 답변 시작 줄이 화면 상단에 올 때까지만 내려가고 그 뒤로는 고정.
                # 아래로만 이동 — 사용자가 직접 더 내려서 읽는 중이면 끌어당기지 않는다.
                target = min(self._typing_anchor_y, bar.maximum())
                if bar.value() < target:
                    bar.setValue(target)
                return
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log.setTextCursor(cursor)
            self._log.ensureCursorVisible()
            bar.setValue(bar.maximum())

        if deferred:
            QTimer.singleShot(0, _do_scroll)
        else:
            _do_scroll()

    def _begin_typing_anchor(self) -> None:
        """답변 시작 줄을 기준점으로 잡아 타이핑 중 화면이 계속 밀리지 않게 한다."""
        self._typing_anchor_y = None
        self._scroll_log_to_bottom()
        QTimer.singleShot(0, self._capture_typing_anchor)

    def _capture_typing_anchor(self) -> None:
        """레이아웃 확정 후 답변 시작 줄의 문서 Y 좌표를 기록."""
        if self._typing_body_start is None:
            return
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        bar = self._log.verticalScrollBar()
        self._typing_anchor_y = max(0, bar.value() + self._log.cursorRect(cursor).top())

    def set_mic_level(self, level: float) -> None:
        """상시 듣기 마이크 레벨 — 하단 주파수 바에 반영."""
        self._waveform.set_level(level)

    def set_speech_threshold_rms(self, speech_rms: float) -> None:
        """인식 감도 임계 — 점선 위치 갱신."""
        self._waveform.set_threshold_rms(speech_rms)

    def begin_user_listening(self) -> None:
        """상시 듣기 시작 — 상태 문구는 set_user_listening_status로 갱신."""
        self._user_listening_active = True

    def set_user_listening_status(self, status: str) -> None:
        """입력창 placeholder에 음성 상태 문구 표시 (푸른·흐린 글씨)."""
        self._user_listening_active = True
        text = (status or "").strip()
        self._input.setPlaceholderText(text or _DEFAULT_INPUT_PLACEHOLDER)
        pal = self._input.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, _PLACEHOLDER_COLOR)
        self._input.setPalette(pal)

    def cancel_user_listening(self) -> None:
        self._user_listening_active = False
        self._input.setPlaceholderText(_DEFAULT_INPUT_PLACEHOLDER)
        pal = self._input.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, _PLACEHOLDER_COLOR)
        self._input.setPalette(pal)

    def begin_stt_pending(self) -> None:
        """STT 대기 — 채팅에 You: ··· 플레이스홀더."""
        if self._stt_pending:
            return
        self.finish_typing()
        self._typing_anchor_y = None
        cursor = self._begin_chat_message_cursor()
        cursor.insertHtml(
            f'<b>You</b>: <a href="iris-stt://pending" '
            f'style="color:{TOKENS.text_muted};text-decoration:none;">···</a>'
        )
        self._log.setTextCursor(cursor)
        self._append_trailing_blank_line()
        self._stt_pending = True
        self._scroll_log_to_bottom()

    def complete_stt_pending(self, text: str) -> bool:
        """플레이스홀더를 인식 텍스트로 교체. pending 없으면 False."""
        body = normalize_chat_body("You", prepare_chat_text(text))
        if not self._stt_pending:
            return False
        if not body:
            self.cancel_stt_pending()
            return True
        import re

        html_doc = self._log.toHtml()
        needle = 'href="iris-stt://pending"'
        if needle not in html_doc:
            self._stt_pending = False
            return False
        body_html = chat_body_to_html(body)
        # QTextEdit가 <a> 안을 <span>으로 감싸므로 non-greedy DOTALL 필요
        updated = re.sub(
            r'<a href="iris-stt://pending"[^>]*>.*?</a>',
            body_html,
            html_doc,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if updated == html_doc:
            self._stt_pending = False
            self.append_message_instant("You", body)
            return True
        bar = self._log.verticalScrollBar()
        pos = bar.value()
        self._log.setHtml(updated)
        bar.setValue(pos)
        self._scroll_log_to_bottom()
        self._stt_pending = False
        self.cancel_user_listening()
        return True

    def cancel_stt_pending(self, *, notice: str = "") -> None:
        """STT 실패/무시 — 플레이스홀더 제거."""
        if not self._stt_pending:
            if notice:
                self.set_user_listening_status(notice)
            return
        import re

        html_doc = self._log.toHtml()
        needle = 'href="iris-stt://pending"'
        if needle in html_doc:
            # ponytail: DOTALL로 <p>…pending…</p>를 잡으면 문서 첫 <p>부터
            # pending까지 통째로 지워 채팅이 증발한다. 앵커만 제거.
            updated = re.sub(
                r'<a href="iris-stt://pending"[^>]*>.*?</a>',
                "",
                html_doc,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if updated != html_doc:
                updated = re.sub(
                    r'<p[^>]*>\s*(?:<span[^>]*>)?(?:<[^>]+>)*You(?:</[^>]+>)*:\s*(?:</span>)?\s*</p>',
                    "",
                    updated,
                    count=1,
                    flags=re.IGNORECASE,
                )
                bar = self._log.verticalScrollBar()
                pos = bar.value()
                self._log.setHtml(updated)
                bar.setValue(pos)
        self._stt_pending = False
        if notice:
            self.set_user_listening_status(notice)

    def complete_user_message_typed(self, text: str) -> None:
        """음성 인식 완료 — pending이면 교체, 없으면 즉시 추가."""
        if self.complete_stt_pending(text):
            return
        self.cancel_user_listening()
        self.append_message_instant("You", text)

    def has_stt_pending(self) -> bool:
        return self._stt_pending

    @property
    def typing_buffer_text(self) -> str:
        """버퍼·스트림 중 누적 본문 (TTS 동기화용)."""
        return self._typing_text

    def append_message(self, who: str, text: str) -> None:
        """Iris 등 — 타이핑 효과로 출력 (TTS 동기화 없음)."""
        self.append_message_typed(who, text, speech_sync=False)

    def _message_block_format(self) -> QTextBlockFormat:
        fmt = QTextBlockFormat()
        fmt.setIndent(0)
        fmt.setTextIndent(0.0)
        fmt.setLeftMargin(0.0)
        return fmt

    def _clear_block_list(self, cursor: QTextCursor, fmt: QTextBlockFormat) -> None:
        lst = cursor.currentList()
        if lst is not None:
            lst.remove(cursor.block())
            cursor.setBlockFormat(fmt)

    def _begin_chat_message_cursor(self) -> QTextCursor:
        """새 메시지 블록을 문서 끝·좌측 정렬로 시작.

        직전 Iris 마크다운(<ul>/<li>)이 남긴 list/indent를 끊지 않으면
        다음 You/Iris 줄이 들여쓰기된 채 이어진다.
        직전 메시지 뒤 빈 줄은 간격으로 남기고, 그 다음 블록에 메시지를 쓴다.
        """
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = self._message_block_format()
        if self._log.toPlainText().strip():
            if not cursor.block().text().strip():
                # 직전 메시지 trailing blank — 간격 유지, 메시지용 새 블록
                cursor.insertBlock(fmt)
            else:
                cursor.insertBlock(fmt)  # 빈 줄
                cursor.insertBlock(fmt)  # 메시지
        else:
            cursor.setBlockFormat(fmt)
        self._clear_block_list(cursor, fmt)
        return cursor

    def _append_trailing_blank_line(self) -> None:
        """메시지 직후 빈 줄 — You/Iris 사이 가독성."""
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not cursor.block().text().strip():
            return
        fmt = self._message_block_format()
        cursor.insertBlock(fmt)
        self._clear_block_list(cursor, fmt)

    def append_message_instant(self, who: str, text: str) -> None:
        """사용자 입력 등 — 타이핑 없이 본문 전체를 즉시 표시."""
        self.finish_typing()
        self._typing_anchor_y = None
        body = normalize_chat_body(who, prepare_chat_text(text))
        if not body:
            return
        cursor = self._begin_chat_message_cursor()
        cursor.insertHtml(f"<b>{html.escape(who)}</b>: ")
        if who.strip().lower() == "iris":
            html_body = iris_message_to_chat_html(body)
            prefetch_chat_html_images(self._log, html_body)
            cursor.insertHtml(html_body)
            msg_id = self.register_tts_message(body)
            cursor.insertHtml(self._speaker_link_html(msg_id))
        else:
            cursor.insertHtml(chat_body_to_html(body))
        self._log.setTextCursor(cursor)
        self._append_trailing_blank_line()
        self._scroll_log_to_bottom()

    def begin_stream_message(
        self,
        who: str,
        *,
        speech_sync: bool = True,
        wait_for_tts_completion: bool = False,
    ) -> None:
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
        self._typing_wait_for_tts_completion = bool(speech_sync and wait_for_tts_completion)
        self._typing_timer.stop()
        self._begin_typing_anchor()

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
        self._begin_typing_anchor()

    def sync_typing_to_speech(
        self,
        duration_ms: float,
        *,
        visible_len: int | None = None,
        spoken_len: int | None = None,
    ) -> None:
        """TTS 재생 길이에 맞춰 대기 중인 본문 타이핑을 시작한다."""
        if self._typing_timer.isActive():
            return
        if not self._typing_text or not self._typing_speech_sync:
            return
        text_len = visible_len if visible_len is not None else len(self._typing_text)
        if spoken_len is not None and spoken_len > 0:
            scaled = scale_typing_duration_ms(duration_ms, text_len, spoken_len)
        else:
            # ponytail: TTS와 동일 속도로 맞추면 "TTS가 들리기 전에 텍스트가 따라오는"
            # 체감이 약해진다. 요청대로 약간 더 빠르게 진행한다.
            scaled = float(duration_ms)
        # ponytail: 더 빠른 타이핑을 강제하되, 최소 글자/초 상한은 함께 보정한다.
        typing_speed_up_factor = 0.85
        min_chars_per_sec = TYPING_SPEECH_MIN_CHARS_PER_SEC * 1.25
        scaled *= float(typing_speed_up_factor)
        self._typing_speech_duration_ms = effective_typing_duration_ms(
            len(self._typing_text),
            scaled,
            min_chars_per_sec=min_chars_per_sec,
        )
        self._typing_speech_start = None
        self._typing_timer.setInterval(TYPING_INTERVAL_MS)
        if not self._typing_timer.isActive():
            self._typing_timer.start()
        self._typing_wait_for_tts_completion = False

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
        typing_speed_up_factor = 0.85
        min_chars_per_sec = TYPING_SPEECH_MIN_CHARS_PER_SEC * 1.25
        scaled *= float(typing_speed_up_factor)
        self._typing_speech_duration_ms = extend_typing_timeline_ms(
            elapsed_ms,
            remaining,
            scaled,
            min_chars_per_sec=min_chars_per_sec,
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
        had_body = bool(self._typing_text) or self._typing_body_start is not None
        self._typing_text = ""
        self._typing_index = 0
        self._typing_speech_sync = False
        self._typing_wait_for_tts_completion = False
        self._typing_speech_duration_ms = None
        self._typing_speech_start = None
        self._typing_body_start = None
        self._typing_render_markdown = False
        if had_body:
            self._append_trailing_blank_line()
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
        if self._typing_wait_for_tts_completion:
            return
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

    def fallback_typing_if_waiting_for_tts(self) -> None:
        """TTS 시작/합성이 실패한 경우만 타이핑 대기를 해제하고 폴백 시작."""
        if not self._typing_wait_for_tts_completion:
            return
        self._typing_wait_for_tts_completion = False
        self._ensure_buffered_typing_fallback()

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
        # setTextCursor는 캐럿을 보이게 하려고 뷰를 끌어내린다 — 읽기 전용 로그라 생략.

    def _render_markdown_body(self) -> None:
        """타이핑 완료 후 마크다운 원문을 렌더링된 HTML로 교체."""
        if self._typing_body_start is None or not self._typing_text:
            return
        body = self._typing_text
        cursor = self._log.textCursor()
        cursor.setPosition(self._typing_body_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        html_body = iris_message_to_chat_html(body)
        prefetch_chat_html_images(self._log, html_body)
        cursor.insertHtml(html_body)
        msg_id = self.register_tts_message(body)
        cursor.insertHtml(self._speaker_link_html(msg_id))

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
            self._append_trailing_blank_line()
            if self._typing_anchor_y is not None:
                self._scroll_log_to_bottom()
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

    def _on_input_changed(self) -> None:
        if self._generating:
            self._input_area.input_bar.send_button.setEnabled(True)
            return
        self._input_area.input_bar.send_button.setEnabled(bool(self._input.text().strip()))

    def set_generating(self, active: bool) -> None:
        """생성 중이면 전송 화살표 → 정지 네모. 클릭 시 stop_clicked."""
        on = bool(active)
        self._generating = on
        btn = self._input_area.input_bar.send_button
        btn.set_stop_mode(on)
        if on:
            btn.setEnabled(True)
        else:
            btn.setEnabled(bool(self._input.text().strip()))

    def is_generating(self) -> bool:
        return self._generating

    def _on_submit_or_stop(self) -> None:
        if self._generating:
            self.stop_clicked.emit()
            return
        self._emit_send()

    def _emit_send(self) -> None:
        t = self._input.text().strip()
        if not t:
            return
        self._input.clear()
        self.send_clicked.emit(t)


if __name__ == "__main__":
    import sys

    from PyQt6.QtWidgets import QApplication, QVBoxLayout

    app = QApplication(sys.argv)
    host = QWidget()
    host.resize(480, 520)
    lay = QVBoxLayout(host)
    panel = ChatPanel()
    lay.addWidget(panel, 1)
    host.show()
    app.processEvents()
    inp = panel._input
    area = panel._input_area
    h0, a0 = inp.height(), area.height()
    inp.setPlainText("a\nb\nc\nd")
    app.processEvents()
    assert inp.height() > h0, (h0, inp.height())
    assert area.height() > a0, (a0, area.height())
    inp.setPlainText("가" * 200)
    app.processEvents()
    assert inp.height() > h0
    print("chat_panel composer grow ok", h0, "->", inp.height(), "area", a0, "->", area.height())
