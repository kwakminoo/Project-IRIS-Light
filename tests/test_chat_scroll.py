"""Exercise the shared transcript in the main and IDE companion layouts."""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QFontDatabase, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionSlider, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.shared.cyberspace_theme import build_cyberspace_qss
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage


class ChatScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Qt's offscreen plugin does not discover Windows system fonts itself.
        for name in ("malgun.ttf", "segoeui.ttf", "arial.ttf", "consola.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))

    def settle(self):
        for _ in range(3):
            self.app.processEvents()

    def wheel(self, panel, delta):
        viewport = panel._log.viewport()
        point = viewport.rect().center()
        event = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)),
                            QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(viewport, event)
        self.settle()

    def test_main_and_companion(self):
        wheel_distances = []
        for mode in ("main", "ide"):
            with self.subTest(mode=mode):
                host = QWidget()
                host.setStyleSheet(build_cyberspace_qss())
                host.resize(480, 720)
                layout = QVBoxLayout(host)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)
                panel = ChatPanel()
                orb, activity = QWidget(), QWidget()
                if mode == "ide":
                    companion = IdeCompanionPage(host)
                    layout.addWidget(companion)
                    companion.mount(orb_spacer=orb, live_activity=activity, chat=panel,
                                    orb_height=160, activity_height=40)
                else:
                    orb.setFixedHeight(160)
                    activity.setFixedHeight(40)
                    layout.addWidget(orb)
                    layout.addWidget(activity)
                    layout.addWidget(panel, 1)
                host.show()
                self.settle()
                for i in range(18):
                    panel.append_message_instant("Iris", f"이전 메시지 {i}\n" + "긴 문장입니다. " * 20)
                self.settle()
                bar = panel._log.verticalScrollBar()
                self.assertEqual(bar.value(), bar.maximum())
                before = bar.value()
                self.wheel(panel, 120)
                wheel_distances.append(before - bar.value())
                self.assertLess(bar.value(), before)
                held = bar.value()
                panel.begin_stream_message("Iris", speech_sync=False)
                self.settle()
                for _ in range(25):
                    panel.append_stream_chunk("긴 응답의 새 줄입니다. " * 12 + "\n")
                    panel._flush_stream_ui()
                    self.settle()
                    self.assertEqual(bar.value(), held)
                panel.end_stream_message()
                self.settle()
                self.assertEqual(bar.value(), held)
                panel.append_message_instant("Iris", "응답 완료 후 새 메시지")
                self.settle()
                self.assertEqual(bar.value(), held)

                # Drag the real scrollbar thumb, then keep that position during output.
                option = QStyleOptionSlider()
                bar.initStyleOption(option)
                thumb = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, option,
                                                   QStyle.SubControl.SC_ScrollBarSlider, bar)
                start = thumb.center()
                QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(bar, QPoint(start.x(), max(20, start.y() - 70)))
                QTest.mouseRelease(bar, Qt.MouseButton.LeftButton,
                                   pos=QPoint(start.x(), max(20, start.y() - 70)))
                self.settle()
                self.assertLess(bar.value(), held)
                held = bar.value()
                panel.append_message_typed("Iris", "타이핑으로 표시되는 긴 응답입니다. " * 100,
                                           speech_sync=False)
                panel._typing_timer.stop()
                self.settle()
                for _ in range(30):
                    panel._type_next_chunk()
                    self.settle()
                    self.assertEqual(bar.value(), held)
                panel.finish_typing()
                self.settle()
                self.assertEqual(bar.value(), held)

                # Scroll down with the wheel: only reaching the tail enables following.
                for _ in range(200):
                    if bar.value() == bar.maximum():
                        break
                    self.wheel(panel, -120)
                self.assertEqual(bar.value(), bar.maximum())
                panel.begin_stream_message("Iris", speech_sync=False)
                for _ in range(20):
                    panel.append_stream_chunk("하단 자동 스크롤 테스트 " * 20 + "\n")
                    panel._flush_stream_ui()
                    self.settle()
                    self.assertEqual(bar.value(), bar.maximum())
                self.wheel(panel, 120)
                held = bar.value()
                for _ in range(5):
                    panel.append_stream_chunk("출력 중 휠로 이전 메시지 보기 " * 20)
                    panel._flush_stream_ui()
                    self.settle()
                    self.assertEqual(bar.value(), held)
                while bar.value() < bar.maximum():
                    self.wheel(panel, -120)
                panel.end_stream_message()
                self.settle()
                self.assertEqual(bar.value(), bar.maximum())
                panel.append_message_typed("Iris", "하단 타이핑 테스트 " * 40, speech_sync=False)
                panel._typing_timer.stop()
                self.settle()
                ticks = 0
                while panel._typing_text and ticks < 1000:
                    panel._type_next_chunk()
                    self.settle()
                    self.assertEqual(bar.value(), bar.maximum())
                    ticks += 1
                self.assertFalse(panel._typing_text)
                self.assertGreater(ticks, 3)

                # Fade changes rendered pixels without changing document geometry.
                self.wheel(panel, 120)
                geometry = panel._log.document().size()
                faded = panel.grab().toImage()
                panel._log._top_fade.setEnabled(False)
                plain = panel.grab().toImage()
                self.assertNotEqual(faded, plain)
                viewport = panel._log.viewport()
                origin = viewport.mapTo(panel, QPoint())
                changed_alpha = False
                for y in range(origin.y(), origin.y() + 24):
                    for x in range(origin.x(), origin.x() + viewport.width()):
                        if faded.pixelColor(x, y).alpha() < plain.pixelColor(x, y).alpha():
                            changed_alpha = True
                self.assertTrue(changed_alpha, "Top fade must reduce actual text opacity")
                self.assertEqual(panel._log.document().size(), geometry)
                panel._log._top_fade.setEnabled(True)
                out = Path(".iris_light_test_tmp")
                out.mkdir(exist_ok=True)
                panel.grab().save(str(out / f"chat-scroll-{mode}.png"))
                panel.clear_transcript()
                panel.append_message_instant("Iris", "새 세션 " * 200)
                self.settle()
                self.assertEqual(bar.value(), bar.maximum())
                host.close()
                host.deleteLater()
                self.settle()
        self.assertEqual(wheel_distances[0], wheel_distances[1])


if __name__ == "__main__":
    unittest.main()
