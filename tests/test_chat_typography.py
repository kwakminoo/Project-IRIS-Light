import tempfile
import sys
import unittest
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QSpinBox

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.storage.database import Database
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.typography import Typography, defaults, manager, normalize
from iris.ui.settings.typography_box import build_typography_box

SAMPLE = (
    "안녕하세요 ABC abc 123\n\n## 제목 Heading\n- 한글 리스트\n- 두 번째\n\n"
    "```python\nprint('한글 ABC 123')\n```\n\n[링크](https://example.com)\n\n"
    + "긴 답변 줄바꿈 테스트입니다. " * 80
)


def _mount(panel: ChatPanel) -> None:
    panel.resize(640, 480)
    panel.show()
    panel.transcript().view()


def _wait_ready(panel: ChatPanel) -> None:
    for _ in range(300):
        if panel.transcript()._page_ready:
            return
        QTest.qWait(10)
    raise AssertionError("H1 transcript did not become ready")


def _probe(panel: ChatPanel) -> dict:
    raw = panel.transcript()._run_js_sync(
        "(function(){"
        "var b=getComputedStyle(document.body);"
        "var h=document.querySelector('.md h2');"
        "var c=document.querySelector('.md code');"
        "var a=document.querySelector('.md a[href^=\"https://\"]');"
        "return {text:document.body.innerText,bodySize:parseFloat(b.fontSize),bodyFamily:b.fontFamily,"
        "headingSize:h?parseFloat(getComputedStyle(h).fontSize):0,"
        "codeSize:c?parseFloat(getComputedStyle(c).fontSize):0,"
        "codeFamily:c?getComputedStyle(c).fontFamily:'',"
        "href:a?a.href:'',ids:[...document.querySelectorAll('.turn[data-msg-id]')].map(t=>t.dataset.msgId),"
        "max:Math.max(0,document.body.scrollHeight-document.body.clientHeight)};"
        "})()"
    )
    if not isinstance(raw, dict):
        raise AssertionError(f"invalid H1 probe: {raw!r}")
    return raw


class TypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _APP
        for name in ("malgun.ttf", "segoeui.ttf", "arial.ttf", "consola.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        cls.app.setFont(QFont("Noto Sans KR", 10))

    def tearDown(self):
        manager.apply(defaults())
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_controls_persist_and_restore(self):
        root = Path.cwd() / ".iris_light_test_tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            path = Path(tmp) / "fonts.db"
            db = Database(path)
            manager.load(db)
            box = build_typography_box(db)
            box.findChild(QSpinBox, "chat_font_size").setValue(22)
            box.findChild(QSpinBox, "typing_chars_per_sec").setValue(40)
            self.assertEqual(manager.get().chat_font_size, 22)
            self.assertEqual(manager.get().typing_chars_per_sec, 40)
            db.close()
            reopened = Database(path)
            manager.apply(defaults())
            manager.load(reopened)
            self.assertEqual(manager.get().chat_font_size, 22)
            self.assertEqual(manager.get().typing_chars_per_sec, 40)
            box.deleteLater()
            box = build_typography_box(reopened)
            box.findChild(QPushButton, "restore_chat_typography").click()
            self.assertEqual(manager.get(), defaults())
            reopened.close()
            box.deleteLater()

    def test_invalid_preferences(self):
        p = normalize({"chat_font_family": "missing-font-123", "chat_font_size": 1000,
                       "code_font_size": "invalid", "typing_chars_per_sec": 1000})
        self.assertEqual(p.chat_font_family, defaults().chat_font_family)
        self.assertEqual(p.chat_font_size, 28)
        self.assertEqual(p.code_font_size, defaults().code_font_size)
        self.assertEqual(p.typing_chars_per_sec, 80)
        self.assertEqual(normalize({"typing_chars_per_sec": "nope"}).typing_chars_per_sec,
                         defaults().typing_chars_per_sec)

    def test_typing_speed_changes_how_many_characters_appear(self):
        from iris.ui.chat.chat_display import plain_typing_step

        self.assertEqual(plain_typing_step(20), (50, 1))
        self.assertEqual(plain_typing_step(80), (25, 2))

    def test_new_markdown_heading_size(self):
        panel = ChatPanel()
        try:
            _mount(panel)
            panel.append_message_instant("Iris", SAMPLE)
            _wait_ready(panel)
            QTest.qWait(150)
            self.assertAlmostEqual(_probe(panel)["headingSize"],
                                   manager.get().chat_font_size + 3, delta=1)
        finally:
            panel.close()
            panel.deleteLater()

    def test_live_matrix(self):
        families = QFontDatabase.families()
        chosen = list(dict.fromkeys([
            QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family(),
            defaults().chat_font_family, "Arial", "Segoe UI",
        ]))
        chosen = [family for family in chosen if family in families][:3]
        self.assertGreaterEqual(len(chosen), 3)
        panels = [ChatPanel(), ChatPanel()]
        try:
            for panel in panels:
                _mount(panel)
                panel.append_message_instant("Iris", SAMPLE)
                _wait_ready(panel)
            QTest.qWait(150)
            for family in chosen:
                for size in (12, 14, 16, 18, 22):
                    with self.subTest(family=family, size=size):
                        prefs = Typography(family, size, defaults().code_font_family, size - 1)
                        manager.apply(prefs)
                        QTest.qWait(30)
                        for panel in panels:
                            probe = _probe(panel)
                            self.assertIn("Heading", probe["text"])
                            self.assertAlmostEqual(probe["bodySize"], size, delta=0.5)
                            self.assertIn(family.lower(), probe["bodyFamily"].lower())
                            self.assertAlmostEqual(probe["headingSize"], size + 3, delta=1)
                            self.assertAlmostEqual(probe["codeSize"], size - 1, delta=0.5)
                            self.assertIn(prefs.code_font_family.lower(), probe["codeFamily"].lower())
                            self.assertGreater(probe["max"], 0)
        finally:
            for panel in panels:
                panel.close()
                panel.deleteLater()

    def test_stream_positions_and_links_survive(self):
        panel = ChatPanel()
        try:
            _mount(panel)
            panel.append_message_instant("Iris", SAMPLE)
            _wait_ready(panel)
            original_ids = _probe(panel)["ids"]
            self.assertEqual(len(original_ids), 1)
            panel.begin_stream_message("Iris", speech_sync=False)
            panel.append_stream_chunk("실시간 답변 ABC 추가 내용")
            panel.end_stream_message()
            panel._typing_timer.stop()
            for _ in range(200):
                if not panel._typing_text:
                    break
                panel._type_next_chunk()
            panel.finish_typing()
            QTest.qWait(150)
            probe = _probe(panel)
            self.assertIn("추가 내용", probe["text"])
            self.assertEqual(probe["href"], "https://example.com/")
            self.assertEqual(probe["ids"][:1], original_ids)
            self.assertEqual(len(set(probe["ids"])), 2)
        finally:
            panel.close()
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
