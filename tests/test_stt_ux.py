"""STT UX: 상태 문구·pending 버블·STATE 라벨."""

from __future__ import annotations

import sys
from unittest import TestCase

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

from iris.core.state_machine import AppState
from iris.ui.window.top_status_header import TopStatusHeader

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat.chat_panel import ChatPanel


class SttUxTests(TestCase):
    def test_listening_status_uses_input_placeholder(self) -> None:
        panel = ChatPanel()
        panel.set_user_listening_status("음성을 인식하고 있습니다")
        self.assertEqual(panel._input.placeholderText(), "음성을 인식하고 있습니다")
        ph = panel._input.palette().color(QPalette.ColorRole.PlaceholderText)
        self.assertEqual(ph.red(), 56)
        self.assertEqual(ph.green(), 189)
        self.assertEqual(ph.blue(), 248)
        self.assertLessEqual(ph.alpha(), 140)
        panel.cancel_user_listening()
        self.assertIn("Iris에게", panel._input.placeholderText())

    def test_stt_pending_completes_to_text(self) -> None:
        panel = ChatPanel()
        panel.begin_stt_pending()
        self.assertTrue(panel.has_stt_pending())
        self.assertIn("iris-stt://pending", panel._log.toHtml())
        self.assertTrue(panel.complete_stt_pending("크롬 열어줘"))
        self.assertFalse(panel.has_stt_pending())
        plain = panel._log.toPlainText()
        self.assertIn("You", plain)
        self.assertIn("크롬 열어줘", plain)
        self.assertNotIn("···", plain)

    def test_stt_pending_cancel_removes_placeholder(self) -> None:
        panel = ChatPanel()
        panel.begin_stt_pending()
        panel.cancel_stt_pending()
        self.assertFalse(panel.has_stt_pending())
        self.assertNotIn("iris-stt://pending", panel._log.toHtml())

    def test_stt_pending_cancel_preserves_prior_messages(self) -> None:
        """끼어들기 후 빈 STT cancel이 이전 채팅을 통째로 지우면 안 된다."""
        panel = ChatPanel()
        panel.append_message_instant("You", "안녕 아이리스")
        panel.append_message_instant("Iris", "안녕하세요")
        panel.begin_stt_pending()
        panel.cancel_stt_pending()
        plain = panel._log.toPlainText()
        self.assertIn("안녕 아이리스", plain)
        self.assertIn("안녕하세요", plain)
        self.assertNotIn("iris-stt://pending", panel._log.toHtml())

    def test_model_status_keeps_runtime_id(self) -> None:
        from iris.infrastructure.ollama_client import OllamaModelInfo

        panel = ChatPanel()
        panel.set_models(
            [OllamaModelInfo(name="gemma4:31b-cloud", catalog_name="Gemma 4")],
            selected="gemma4:31b-cloud",
        )
        self.assertEqual(panel.current_model(), "gemma4:31b-cloud")
        panel.set_model_status("(클라우드 모델 확인 중…)")
        self.assertEqual(panel.current_model(), "gemma4:31b-cloud")
        self.assertIn("클라우드", panel._model_combo.currentText())

    def test_model_status_alone_is_not_a_model(self) -> None:
        panel = ChatPanel()
        panel.set_model_status("(클라우드 모델 확인 중…)")
        self.assertEqual(panel.current_model(), "")

    def test_state_chip_accepts_stt_llm_tts_labels(self) -> None:
        header = TopStatusHeader()
        header.set_app_state(AppState.PROCESSING, label="STT")
        self.assertEqual(header.status_label.text(), "STT")
        header.set_app_state(AppState.PROCESSING, label="LLM")
        self.assertEqual(header.status_label.text(), "LLM")
        header.set_app_state(AppState.RESPONDING, label="TTS")
        self.assertEqual(header.status_label.text(), "TTS")
        header.set_app_state(AppState.LISTENING, label="LISTEN")
        self.assertEqual(header.status_label.text(), "LISTEN")
