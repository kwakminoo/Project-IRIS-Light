"""상황별 음성 명령 힌트 — 사이드바 아이콘 그리드 위의 회색 안내 문구.

전화가 울리면 여기에 "전화 받아줘" 가 뜬다. 지금 말하면 통하는 문장만 보여
주므로, 사용자는 무엇을 말해야 하는지 외우지 않아도 된다.

인지 상태나 발음 문제로 말하지 못할 수 있다는 게 이 위젯이 존재하는 이유다.
그래서 **읽을 수 있는 안내인 동시에 누를 수 있는 버튼**으로 만들었다.
말로 해도 되고, 안 되면 그냥 누르면 된다.

색은 평소엔 흐린 회색이라 눈에 걸리지 않는다. 전화처럼 급한 상황에서만
살짝 밝아진다 — 화면을 어지럽히지 않으면서 필요할 때 보이도록.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from iris.runtime.voice_intents import IntentContext, VoiceIntent, intent_prompt
from iris.ui.shared.theme_tokens import TOKENS

# 상황마다 보여 줄 인텐트와 순서. prompts_for() 는 전부 주지만
# 사이드바는 좁아서 지금 상황에서 가장 중요한 것만 추린다.
_CONTEXT_INTENTS: dict[IntentContext, tuple[VoiceIntent, ...]] = {
    IntentContext.CALL_RINGING: (VoiceIntent.ANSWER_CALL, VoiceIntent.REJECT_CALL),
    IntentContext.CALL_ACTIVE: (VoiceIntent.HANG_UP,),
    IntentContext.ALERT_PENDING: (VoiceIntent.READ_ALERT, VoiceIntent.REPEAT_ALERT),
    IntentContext.IDLE: (),
}

# 급한 상황에서만 조금 밝게. 그 외엔 배경에 묻히는 회색.
_URGENT_CONTEXTS = (IntentContext.CALL_RINGING,)


class VoiceHintPanel(QWidget):
    """지금 말하면 되는 문장들. 누르면 같은 동작이 실행된다."""

    prompt_activated = pyqtSignal(str)  # VoiceIntent.value

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VoiceHintPanel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 2, 10, 4)
        self._lay.setSpacing(2)

        self._caption = QLabel(self)
        self._caption.setObjectName("VoiceHintCaption")
        self._caption.setWordWrap(True)
        self._lay.addWidget(self._caption)

        self._buttons: list[QPushButton] = []
        self._context = IntentContext.IDLE
        self._enabled = True
        self._caption_text = ""
        self.set_context(IntentContext.IDLE)

    # ------------------------------------------------------------------

    def set_enabled_by_pref(self, enabled: bool) -> None:
        """설정에서 힌트를 끈 경우 — 전체를 숨긴다."""
        self._enabled = bool(enabled)
        self._refresh_visibility()

    def set_context(self, context: IntentContext, *, caption: str = "") -> None:
        """상황이 바뀌면 문장 목록을 다시 그린다."""
        self._context = context
        self._caption_text = (caption or "").strip()
        self._rebuild()

    def current_context(self) -> IntentContext:
        return self._context

    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        for btn in self._buttons:
            # setParent(None) 을 먼저 해야 한다. deleteLater() 만 부르면 실제
            # 삭제가 다음 이벤트 루프로 미뤄져서, 그 사이에 이전 상황의 문장이
            # 새 문장과 같이 보인다.
            self._lay.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._buttons = []

        urgent = self._context in _URGENT_CONTEXTS
        base = TOKENS.text_secondary if urgent else TOKENS.text_muted

        if self._caption_text:
            self._caption.setText(self._caption_text)
            self._caption.setStyleSheet(
                f"color: {base}; font-size: 10px; background: transparent;"
                " border: none; padding: 0;"
            )
            self._caption.show()
        else:
            self._caption.hide()

        for intent in _CONTEXT_INTENTS.get(self._context, ()):
            prompt = intent_prompt(intent)
            if not prompt:
                continue
            self._lay.addWidget(self._make_prompt_button(intent, prompt, base))

        self._refresh_visibility()

    def _make_prompt_button(
        self, intent: VoiceIntent, prompt: str, color: str
    ) -> QPushButton:
        btn = QPushButton(f'"{prompt}"', self)
        btn.setObjectName("VoiceHintPrompt")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip(f"이렇게 말하거나, 눌러도 됩니다 — {prompt}")
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # padding 을 명시하지 않으면 테마의 QPushButton { padding: 6px 12px }가
        # 그대로 먹어 좁은 사이드바에서 글자가 잘린다.
        btn.setStyleSheet(
            f"""
            QPushButton#VoiceHintPrompt {{
                background: transparent;
                border: none;
                padding: 1px 0;
                text-align: left;
                color: {color};
                font-size: 11px;
            }}
            QPushButton#VoiceHintPrompt:hover {{
                color: {TOKENS.neon_cyan};
            }}
            """
        )
        btn.clicked.connect(lambda _checked=False, i=intent: self.prompt_activated.emit(i.value))
        self._buttons.append(btn)
        return btn

    def _refresh_visibility(self) -> None:
        has_content = bool(self._buttons) or bool(self._caption_text)
        self.setVisible(self._enabled and has_content)
