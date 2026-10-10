"""Regression coverage through actual Qt stream completion and Markdown rendering."""
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEvent
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_display import assistant_visible_text
from iris.ui.chat.chat_blocks import parse_copy_anchor
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisPanel


class ResponseEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_response_types_across_chunk_boundaries_and_completion_modes(self):
        cases = [
            ("**Iris**: Iris: 완료했습니다.", "완료했습니다."),
            ("**Iris:** " + "긴 답변입니다.\n" * 100 + "끝입니다.", "끝입니다."),
            ("**Iris**: 첫 줄\\\n둘째 줄\n마지막 줄", "마지막 줄"),
            ('**Iris**: IDE에 `C:\\Users\\serin\\Project-IRIS-Light`를 열었습니다.', '를 열었습니다.'),
            ('설명\n```python\nprint("hello")\n```\n완료했습니다.', '완료했습니다.'),
            ('코드\n```python\nprint("hello")', 'print("hello")'),
        ]
        for source, ending in cases:
            for size in (1, 7, len(source)):
                for final in (None, source):
                    for speech in (False, True):
                        with self.subTest(source=source[:40], size=size, final=final is not None, speech=speech):
                            panel = ChatPanel()
                            workspace = WorkspaceIrisPanel(name_prefix="ResponseEnd", placeholder="test")
                            panel.append_message_instant("You", "이전 메시지")
                            workspace.append_user("이전 메시지")
                            panel.begin_stream_message("Iris", speech_sync=speech)
                            for start in range(0, len(source), size):
                                chunk = source[start:start + size]
                                panel.append_stream_chunk(chunk)
                                workspace.append_iris_chunk(chunk)
                            self.assertEqual(panel._typing_text, source)
                            panel.end_stream_message(final)
                            panel.finish_typing()
                            workspace.end_iris(final)
                            workspace.chat.finish_typing()
                            main = panel._log.toPlainText()
                            other = workspace._log.toPlainText()
                            self.assertIn("이전 메시지", main)
                            self.assertNotIn("**Iris", main)
                            self.assertEqual(main.count("Iris:"), 1)
                            self.assertNotIn("```", main)
                            self.assertNotIn("\\\n", main)
                            self.assertIn(ending, main)
                            self.assertRegex(main, re.escape(ending) + r"\s*\n\[재생\]\s*$")
                            self.assertEqual(main.split("Iris:", 1)[1].replace("[재생]", "").strip(),
                                             other.split("Iris:", 1)[1].replace("[재생]", "").strip())
                            self.assertNotIn("[재생]", panel.get_tts_text("last"))
                            panel.close()
                            workspace.close()
                            panel.deleteLater()
                            workspace.deleteLater()
                            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_paths_keep_inline_code_delimiters(self):
        source = r'IDE에 `C:\Users\serin\Project-IRIS-Light`. 다음은 `value`입니다.'
        visible = assistant_visible_text(source, streaming=False)
        self.assertEqual(visible, 'IDE에 `작업 폴더`. 다음은 `value`입니다.')

    def test_unclosed_code_preserves_literal_terminal_backtick(self):
        panel = ChatPanel()
        source = '```text\nliteral `'
        panel.begin_stream_message("Iris", speech_sync=False)
        panel.append_stream_chunk(source)
        panel.end_stream_message(source)
        panel.finish_typing()
        href = re.search(r'href="(iris-copy://[^"]+)"', panel._log.toHtml())[1]
        self.assertEqual(parse_copy_anchor(href), 'literal `\n')
        panel.close()

    def test_stream_types_one_character_at_a_time(self):
        panel = ChatPanel()
        source = "가나다라마바사"
        panel.begin_stream_message("Iris", speech_sync=False)
        panel.append_stream_chunk(source)
        self.assertEqual(panel._typing_text, source)
        self.assertEqual(panel._typing_index, 0)
        self.assertNotIn(source, panel._log.toPlainText())
        self.assertTrue(panel._typing_timer.isActive())
        panel._typing_timer.stop()
        panel._type_next_chunk()
        self.assertIn("가", panel._log.toPlainText())
        self.assertNotIn(source, panel._log.toPlainText())
        panel.end_stream_message(source)
        self.assertTrue(panel._typing_timer.isActive())
        self.assertNotIn(source, panel._log.toPlainText())
        while panel._typing_text:
            panel._typing_timer.stop()
            panel._type_next_chunk()
        self.assertIn(source, panel._log.toPlainText())
        panel.close()


if __name__ == "__main__":
    unittest.main()
