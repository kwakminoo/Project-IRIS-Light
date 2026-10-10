import json
import tempfile
import unittest
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QComboBox, QSpinBox, QPushButton
from PyQt6.QtGui import QFont, QFontDatabase
from iris.ui.chat.typography import manager, defaults, normalize, Typography, KEY
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.settings.typography_box import build_typography_box
from iris.storage.database import Database

SAMPLE = "안녕하세요 ABC abc 123\n\n## 제목 Heading\n- 한글 리스트\n- 두 번째\n\n```python\nprint('한글 ABC 123')\n```\n\n|항목|값|\n|---|---|\n|한글 테스트|ABC 123|\n\n" + "긴 답변 줄바꿈 테스트입니다. " * 80


class TypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setFont(QFont("Noto Sans KR", 10))

    def tearDown(self):
        manager.apply(defaults())

    def test_controls_persist_and_restore(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / ".iris_light_test_tmp") as tmp:
            path = Path(tmp) / "fonts.db"
            db = Database(path)
            manager.load(db)
            box = build_typography_box(db)
            sizes = box.findChild(QSpinBox, "chat_font_size")
            sizes.setValue(22)
            speed = box.findChild(QSpinBox, "typing_chars_per_sec")
            speed.setValue(40)
            self.assertEqual(manager.get().chat_font_size, 22)
            self.assertEqual(manager.get().typing_chars_per_sec, 40)
            db._conn.close()
            reopened = Database(path)
            manager.apply(defaults())
            manager.load(reopened)
            self.assertEqual(manager.get().chat_font_size, 22)
            self.assertEqual(manager.get().typing_chars_per_sec, 40)
            box.deleteLater()
            box = build_typography_box(reopened)
            box.findChild(QPushButton, "restore_chat_typography").click()
            self.assertEqual(manager.get(), defaults())
            reopened._conn.close()
            box.deleteLater()

    def test_invalid_preferences(self):
        p = normalize({"chat_font_family": "missing-font-123", "chat_font_size": 1000, "code_font_size": "invalid",
                       "typing_chars_per_sec": 1000})
        self.assertEqual(p.chat_font_family, defaults().chat_font_family)
        self.assertEqual(p.chat_font_size, 28)
        self.assertEqual(p.code_font_size, defaults().code_font_size)
        self.assertEqual(p.typing_chars_per_sec, 80)
        kept = normalize({"typing_chars_per_sec": "nope"})
        self.assertEqual(kept.typing_chars_per_sec, defaults().typing_chars_per_sec)

    def test_typing_speed_changes_how_many_characters_appear(self):
        from iris.ui.chat.chat_display import plain_typing_step

        self.assertEqual(plain_typing_step(20), (50, 1))
        self.assertEqual(plain_typing_step(80), (25, 2))
        fast = defaults()
        fast.typing_chars_per_sec = 80
        manager.apply(fast)
        panel = ChatPanel()
        panel.begin_stream_message("Iris", speech_sync=False)
        panel.append_stream_chunk("가나다라마바사아")
        panel._typing_timer.stop()
        panel._type_next_chunk()
        self.assertEqual(panel._typing_index, 2)
        panel.close()

    def test_new_markdown_heading_size(self):
        panel = ChatPanel()
        panel.append_message_instant("Iris", SAMPLE)
        block = panel._log.document().begin()
        found = False
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and "Heading" in frag.text():
                    self.assertEqual(frag.charFormat().font().pixelSize(), manager.get().chat_font_size + 3)
                    found = True
                it += 1
            block = block.next()
        self.assertTrue(found)
        panel.deleteLater()

    def test_live_matrix(self):
        families = QFontDatabase.families()
        chosen = list(dict.fromkeys([QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family(), defaults().chat_font_family, "Arial", "Segoe UI"]))
        chosen = [f for f in chosen if f in families]
        chosen = chosen[:3]
        self.assertGreaterEqual(len(chosen), 3)
        main, ide = ChatPanel(), ChatPanel()
        main.resize(800, 600)
        ide.resize(420, 600)
        main.show()
        ide.show()
        for panel in (main, ide):
            panel.append_message_instant("You", SAMPLE)
            panel.append_message_instant("Iris", SAMPLE)
        original = main._log.toPlainText()
        for family in chosen:
            for size in (12, 14, 16, 18, 22):
                with self.subTest(family=family, size=size):
                    p = Typography(family, size, defaults().code_font_family, size - 1)
                    manager.apply(p)
                    self.app.processEvents()
                    for panel in (main, ide):
                        log = panel._log
                        doc = log.document()
                        self.assertEqual(log.toPlainText(), original)
                        self.assertEqual(doc.defaultFont().pixelSize(), size)
                        self.assertEqual(doc.defaultFont().family(), family)
                        self.assertGreater(log.verticalScrollBar().maximum(), 0)
                        block = doc.begin()
                        code_seen = heading_seen = False
                        while block.isValid():
                            it = block.begin()
                            while not it.atEnd():
                                frag = it.fragment()
                                if frag.isValid():
                                    f = frag.charFormat().font()
                                    if "print" in frag.text():
                                        self.assertEqual(f.pixelSize(), size - 1)
                                        self.assertEqual(f.family(), p.code_font_family)
                                        code_seen = True
                                    if "Heading" in frag.text():
                                        self.assertEqual(f.pixelSize(), size + 3)
                                        heading_seen = True
                                it += 1
                            layout = block.layout()
                            for i in range(layout.lineCount()):
                                line = layout.lineAt(i)
                                self.assertGreater(line.height(), 0)
                                self.assertGreaterEqual(layout.boundingRect().height() + 1, line.y() + line.height())
                            block = block.next()
                        self.assertTrue(code_seen and heading_seen)
                    main._log.verticalScrollBar().setValue(0)
                    ide._log.verticalScrollBar().setValue(0)
                    self.app.processEvents()
                    for name, panel in (("main", main), ("ide", ide)):
                        panel.grab().save(str(Path.cwd() / ".iris_light_test_tmp" / f"typography-{name}-{chosen.index(family)}-{size}.png"))
        out = Path.cwd() / ".iris_light_test_tmp"
        main.grab().save(str(out / "typography-main-22.png"))
        ide.grab().save(str(out / "typography-ide-22.png"))
        print("TYPOGRAPHY", json.dumps({"defaults": defaults().__dict__, "families": chosen,
              "screens": [{"dpi": s.logicalDotsPerInch(), "dpr": s.devicePixelRatio()} for s in self.app.screens()]}, ensure_ascii=True))
        main.close()
        ide.close()
        main.deleteLater()
        ide.deleteLater()

    def test_stream_positions_and_links_survive(self):
        panel = ChatPanel()
        panel.append_message_instant("Iris", SAMPLE)
        panel.begin_stream_message("Iris")
        panel.append_stream_chunk("실시간 답변 ABC")
        before = panel._stream_block_start
        body_before = panel._typing_body_start
        manager.apply(Typography(defaults().chat_font_family, 18, defaults().code_font_family, 17))
        self.assertEqual(panel._stream_block_start, before)
        self.assertEqual(panel._typing_body_start, body_before)
        self.assertIn("iris-msg-", panel._log.document().toHtml())
        panel.append_stream_chunk(" 추가 내용")
        panel.end_stream_message()
        panel.finish_typing()
        self.assertIn("추가 내용", panel._log.toPlainText())
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
