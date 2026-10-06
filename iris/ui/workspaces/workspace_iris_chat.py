"""Mail/calendar shell around the same ChatPanel used by the IDE."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.widgets.particle_visualizer import ParticleVisualizer
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage, EMAIL_ORB_HEIGHT, EMAIL_ORB_SCALE


class WorkspaceIrisPanel(IdeCompanionPage):
    """Keep workspace APIs while delegating all chat behavior to ChatPanel."""

    chat_send = pyqtSignal(str, list)
    chat_stop = pyqtSignal()

    def __init__(self, *, name_prefix: str, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"{name_prefix}IrisPanel")
        self._default_placeholder = placeholder
        self.orb = ParticleVisualizer(self)
        self.orb.set_size_scale(EMAIL_ORB_SCALE)
        spacer = QWidget(self)
        self._activity_host = QWidget(self)
        self._activity_host.setObjectName(f"{name_prefix}ActivityHost")
        self._activity_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._activity_lay = QVBoxLayout(self._activity_host)
        self._activity_lay.setContentsMargins(0, 0, 0, 0)
        self._activity_lay.setSpacing(0)
        self._live_mounted: QWidget | None = None
        self.chat = ChatPanel()
        self.chat._orb_visualizer = self.orb
        self.chat._input.setPlaceholderText(placeholder)
        # The main panel owns the application's model selection.
        self.chat._input_area.input_bar._model_shell.hide()
        self.chat.send_clicked.connect(self.chat_send.emit)
        self.chat.stop_clicked.connect(self.chat_stop.emit)
        self._log = self.chat._log
        self._input_area = self.chat._input_area
        self.mount(orb_spacer=spacer, live_activity=self._activity_host,
                   chat=self.chat, orb_height=EMAIL_ORB_HEIGHT, activity_height=0)
        self._activity_host.hide()
        self.embed_orb(self.orb, spacer)

    def set_listening_status(self, status: str) -> None:
        self.chat._input.setPlaceholderText((status or "").strip() or self._default_placeholder)

    def reset_listening_status(self) -> None:
        self.set_listening_status("")

    def set_mic_level(self, level: float) -> None:
        self.chat.set_mic_level(level)

    def set_generating(self, active: bool) -> None:
        self.chat.set_generating(active)

    def append_user(self, text: str) -> None:
        self.end_iris()
        self.chat.append_message_instant("You", text)

    def append_iris_chunk(self, text: str) -> None:
        if not text:
            return
        if not self.chat._stream_active:
            self.chat.begin_stream_message("Iris", speech_sync=False)
        self.chat.append_stream_chunk(text)

    def end_iris(self, final_text: str | None = None) -> None:
        if self.chat._stream_active:
            self.chat.end_stream_message(final_text)
        elif final_text:
            self.chat.append_message_instant("Iris", final_text)

    def append_iris_tool(self, text: str) -> None:
        self.end_iris()
        if text:
            self.chat.insert_tool_block(title="Tool", output=text, status="ok")

    def insert_tool_block(self, **kwargs) -> str:
        self.end_iris()
        return self.chat.insert_tool_block(**kwargs)

    def append_iris_error(self, text: str) -> None:
        self.end_iris()
        if text:
            self.chat.append_error_message(text, text)

    def set_orb_state(self, state_name: str) -> None:
        self.orb.set_state(state_name)

    def mount_live_activity(self, live: QWidget, *, height: int = 96) -> None:
        """IDE Companion과 같은 위치(오브 아래)에 Live Activity 마운트."""
        self.chat.reset_height_expansion()
        h = max(72, min(140, int(height)))
        live.setMinimumHeight(h)
        live.setMaximumHeight(h)
        live.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._activity_host.setMinimumHeight(h)
        self._activity_host.setMaximumHeight(h)
        self._activity_host.show()
        # addWidget이 이전 부모에서 원자적으로 옮김 (orphan 창 금지)
        self._activity_lay.addWidget(live)
        self._live_mounted = live
        live.show()

    def has_live_activity(self) -> bool:
        return self._live_mounted is not None

    def clear_live_slot(self) -> None:
        """슬롯만 비움 — 위젯 reparent는 호출측 addWidget이 담당."""
        self.chat.reset_height_expansion()
        self._live_mounted = None
        self._activity_host.setMinimumHeight(0)
        self._activity_host.setMaximumHeight(0)
        self._activity_host.hide()
