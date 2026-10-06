"""Exercise the real workspace pages and their shared IDE composer."""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QObject, Qt, QMimeData, QUrl
from PyQt6.QtGui import QDropEvent, QKeyEvent
from PyQt6.QtCore import QPointF, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.calendar_workspace_page import CalendarWorkspacePage


def window_methods():
    """Run real window methods without starting unrelated services in MainWindow."""
    tree = ast.parse(Path('iris/ui/window/main_window.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    names = {'_on_email_chat_send', '_on_calendar_chat_send', '_prepare_workspace_chat_attachments',
             '_stop_workspace_chat', '_attach_os_drop_paths'}
    namespace = {'HermesChatWorker': Mock()}
    module = ast.Module(body=[n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<workspace-window-methods>', 'exec'), namespace)
    return type('WindowHarness', (QObject,), {name: namespace[name] for name in names}), namespace


class WorkspaceChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_signal_keyboard_attachment_removal_and_stop(self):
        for page_type, mode in ((EmailWorkspacePage, 'email'), (CalendarWorkspacePage, 'calendar')):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                page = page_type()
                page.resize(1100, 850)
                page.show()
                self.app.processEvents()
                chat = page.iris_panel.chat
                self.assertIs(type(chat), ChatPanel)
                sends, stops = [], []
                getattr(page, f'{mode}_chat_send').connect(lambda text, paths: sends.append((text, paths)))
                page.iris_panel.chat_stop.connect(lambda: stops.append(True))
                file = Path(directory) / '첨부 파일.txt'
                file.write_text('shared attachment evidence', encoding='utf-8')
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(file))])
                drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                chat.dropEvent(drop)
                self.assertTrue(drop.isAccepted())
                self.assertEqual(chat._input_area.attachment_strip.paths(), [str(file)])
                chat.attach_drop_paths([str(file)])
                self.assertEqual(len(chat._input_area.attachment_strip.paths()), 1)
                chat._input.setFocus()
                chat._input.setText('첫 줄')
                QApplication.sendEvent(chat._input, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                    Qt.KeyboardModifier.ShiftModifier, '\r'))
                chat._input.insertPlainText('둘째 줄')
                QTest.keyClick(chat._input, Qt.Key.Key_Return)
                self.assertEqual(sends, [('첫 줄\n둘째 줄', [str(file)])])
                self.assertEqual(chat._input.text(), '')
                self.assertEqual(chat._input_area.attachment_strip.paths(), [])
                chat.attach_drop_paths([str(file)])
                chat._emit_send()
                self.assertEqual(sends[-1], ('', [str(file)]))
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

    def test_background_extraction_and_cancellation(self):
        Harness, _ = window_methods()
        for mode, page_type in (('email', EmailWorkspacePage), ('calendar', CalendarWorkspacePage)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / 'background.txt'
                file.write_text('background evidence', encoding='utf-8')
                window = Harness()
                page = page_type()
                setattr(window, f'_{mode}_page', page)
                setattr(window, f'_{mode}_history', [])
                send = Mock()
                setattr(window, f'_on_{mode}_chat_send', send)
                setattr(window, f'_on_{mode}_chat_failed', Mock())
                window._stop_tts_playback = Mock()
                window._sync_voice_conversation_state = Mock()
                window._prepare_workspace_chat_attachments(mode, 'read', [str(file)])
                worker = getattr(window, f'_{mode}_chat_worker')
                deadline = time.monotonic() + 5
                while not send.called and time.monotonic() < deadline:
                    self.app.processEvents()
                    QTest.qWait(10)
                worker.wait(5000)
                self.assertTrue(send.called)
                self.assertIn('background evidence', send.call_args.args[2].model_content('read'))
                self.assertFalse(getattr(window, f'_{mode}_busy'))
                self.assertFalse(page.iris_panel.chat.is_generating())

                send.reset_mock()
                window._prepare_workspace_chat_attachments(mode, 'cancel', [str(file)])
                worker = getattr(window, f'_{mode}_chat_worker')
                window._stop_workspace_chat(mode)
                worker.wait(5000)
                self.app.processEvents()
                self.assertFalse(send.called)
                self.assertFalse(getattr(window, f'_{mode}_busy'))
                self.assertIsNone(getattr(window, f'_{mode}_chat_worker'))
                self.assertFalse(page.iris_panel.chat.is_generating())
                self.assertTrue(window._stop_tts_playback.called)
                page.deleteLater()
                self.app.processEvents()

    def test_attachment_contents_reach_each_workspace_agent(self):
        Harness, namespace = window_methods()
        for mode, page_type in (('email', EmailWorkspacePage), ('calendar', CalendarWorkspacePage)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                from iris.runtime.attachment_context import prepare_attachments
                file = Path(directory) / 'evidence.txt'
                file.write_text('unique document contents 5278', encoding='utf-8')
                result = prepare_attachments([str(file)])
                window = Harness()
                page = page_type()
                setattr(window, f'_{mode}_page', page)
                setattr(window, f'_{mode}_busy', False)
                setattr(window, f'_{mode}_history', [])
                window._settings = SimpleNamespace(hermes_enabled=True, ollama_base_url='',
                    hermes_base_url='', hermes_api_key='', hermes_command='')
                window._hermes_online = True
                window._db = None
                window._chat = SimpleNamespace(current_model=lambda: 'test-model')
                window._current_email_account = lambda: None
                window._stop_tts_playback = Mock()
                window._begin_auto_tts_response = Mock()
                for suffix in ('tool', 'chunk', 'finished', 'failed'):
                    setattr(window, f'_on_{mode}_chat_{suffix}', Mock())
                namespace['HermesChatWorker'].reset_mock()
                with (patch('iris.infrastructure.hermes_client.resolve_hermes_inference',
                           return_value=SimpleNamespace(label='test')),
                     patch('iris.infrastructure.email_client.build_agent_context', return_value='email context'), \
                     patch('iris.infrastructure.calendar_agent.build_calendar_agent_context', return_value='calendar context'), \
                     patch('iris.infrastructure.kr_holiday_client.load_cached_holidays', return_value=[]), \
                     patch('iris.storage.calendar_events.list_events', return_value=[])):
                    getattr(window, f'_on_{mode}_chat_send')('read this', [str(file)], result)
                messages = namespace['HermesChatWorker'].call_args.args[2]
                self.assertIn('unique document contents 5278', messages[-1]['content'])
                self.assertIn('evidence.txt', messages[-1]['content'])
                self.assertNotIn(str(file), messages[-1]['content'])
                self.assertIn('evidence.txt', page.iris_panel._log.toPlainText())
                self.assertTrue(page.iris_panel.chat.is_generating())
                page.deleteLater()
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
