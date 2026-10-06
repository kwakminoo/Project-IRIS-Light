"""메일/캘린더 오른쪽 칸은 IDE와 같은 채팅 호스트를 쓴다."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.calendar_workspace_page import CalendarWorkspacePage
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage


class WorkspaceChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_host_keyboard_attachment_and_stop(self):
        for page_type in (EmailWorkspacePage, CalendarWorkspacePage):
            with self.subTest(page=page_type.__name__), tempfile.TemporaryDirectory() as directory:
                page = page_type()
                self.assertFalse(hasattr(page, "iris_panel"))
                host = IdeCompanionPage()
                chat = ChatPanel()
                host.mount(
                    orb_spacer=QWidget(),
                    live_activity=QWidget(),
                    chat=chat,
                    activity_height=96,
                )
                page.resize(1100, 850)
                page.show()
                self.app.processEvents()
                page.place_chat_host(host)
                self.assertIs(host.parent(), page._chat_host)

                sends, stops = [], []
                chat.send_clicked.connect(lambda text, paths: sends.append((text, paths)))
                chat.stop_clicked.connect(lambda: stops.append(True))
                file = Path(directory) / "첨부 파일.txt"
                file.write_text("shared attachment evidence", encoding="utf-8")
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(file))])
                drop = QDropEvent(
                    QPointF(10, 10),
                    Qt.DropAction.CopyAction,
                    mime,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                chat.dropEvent(drop)
                self.assertTrue(drop.isAccepted())
                self.assertEqual(chat._input_area.attachment_strip.paths(), [str(file)])
                chat.attach_drop_paths([str(file)])
                self.assertEqual(len(chat._input_area.attachment_strip.paths()), 1)
                chat._input.setFocus()
                chat._input.setText("첫 줄")
                QApplication.sendEvent(
                    chat._input,
                    QKeyEvent(
                        QEvent.Type.KeyPress,
                        Qt.Key.Key_Return,
                        Qt.KeyboardModifier.ShiftModifier,
                        "\r",
                    ),
                )
                chat._input.insertPlainText("둘째 줄")
                QTest.keyClick(chat._input, Qt.Key.Key_Return)
                self.assertEqual(sends, [("첫 줄\n둘째 줄", [str(file)])])
                self.assertEqual(chat._input.text(), "")
                self.assertEqual(chat._input_area.attachment_strip.paths(), [])
                chat.attach_drop_paths([str(file)])
                chat._emit_send()
                self.assertEqual(sends[-1], ("", [str(file)]))
                chat.attach_drop_paths([str(file)])
                chat._input_area.attachment_strip._remove(str(file))
                self.assertFalse(chat._input_area.input_bar.send_button.isEnabled())
                chat.set_generating(True)
                QTest.mouseClick(chat._input_area.input_bar.send_button, Qt.MouseButton.LeftButton)
                self.assertEqual(stops, [True])
                self.assertEqual(len(sends), 2)
                chat.set_generating(False)
                page.close()
                page.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
