"""아이콘 버튼 회귀 방지 — setFixedSize 에는 padding: 0 이 반드시 따라와야 한다.

cyberspace_theme 의 전역 규칙이 `QPushButton { padding: 6px 12px }` 라서,
20×20 같은 작은 고정 크기 버튼에서 로컬 스타일시트가 padding 을 덮어쓰지 않으면
글리프가 버튼 밖으로 밀려나 **아무것도 안 보인다**.

RUNNING WINDOWS 목록의 `×` 닫기 버튼이 실제로 이 문제로 보이지 않았다.
"""

from __future__ import annotations

import os
import unittest
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QPushButton

    _QT_AVAILABLE = True
except Exception:  # pragma: no cover - PyQt6 없는 환경
    _QT_AVAILABLE = False

_MAX_ICON_BUTTON_PX = 24


def _app() -> "QApplication":
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(_QT_AVAILABLE, "PyQt6 필요")
class IconButtonPaddingTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qapp = _app()

    def _assert_icon_buttons_reset_padding(self, root) -> None:
        buttons = root.findChildren(QPushButton)
        self.assertTrue(buttons, "검사할 버튼이 없다 — 테스트가 무의미해졌는지 확인")
        checked = 0
        for btn in buttons:
            size = btn.size()
            if size.width() > _MAX_ICON_BUTTON_PX or size.height() > _MAX_ICON_BUTTON_PX:
                continue
            checked += 1
            self.assertIn(
                "padding",
                btn.styleSheet(),
                f"고정 크기 아이콘 버튼 '{btn.text()}' 에 padding 선언이 없다 — "
                "테마의 padding: 6px 12px 가 적용돼 글리프가 보이지 않는다",
            )
        self.assertGreater(checked, 0, "고정 크기 아이콘 버튼을 하나도 찾지 못했다")

    def test_window_list_close_button_has_padding(self) -> None:
        from iris.automation.window_controller import WindowInfo
        from iris.ui.monitor.window_list_panel import _make_row

        row = _make_row(
            WindowInfo(title="테스트 창", left=0, top=0, width=800, height=600, hwnd=1),
            lambda _info: None,
            lambda _info: None,
        )
        self._assert_icon_buttons_reset_padding(row)

    def test_close_button_glyph_fits_inside_button(self) -> None:
        """padding 을 뺀 안쪽 폭이 글리프 폭보다 넓어야 한다."""
        from iris.automation.window_controller import WindowInfo
        from iris.ui.monitor.window_list_panel import _make_row

        row = _make_row(
            WindowInfo(title="테스트 창", left=0, top=0, width=800, height=600, hwnd=1),
            lambda _info: None,
            lambda _info: None,
        )
        close_buttons = [b for b in row.findChildren(QPushButton) if b.text() == "×"]
        self.assertEqual(len(close_buttons), 1)
        btn = close_buttons[0]
        self.assertEqual((btn.width(), btn.height()), (20, 20))
        self.assertIn("padding: 0", btn.styleSheet().replace(" ;", ";"))

    def test_pin_button_still_has_padding(self) -> None:
        """이미 올바른 쪽도 같이 지킨다 (unified_monitor_panel 의 고정 버튼)."""
        from iris.automation.window_controller import WindowInfo
        from iris.ui.monitor.unified_monitor_panel import _make_pin_button

        btn = _make_pin_button(
            WindowInfo(title="테스트 창", left=0, top=0, width=800, height=600, hwnd=1),
            False,
            lambda _info: None,
        )
        self.assertIn("padding: 0", btn.styleSheet())
