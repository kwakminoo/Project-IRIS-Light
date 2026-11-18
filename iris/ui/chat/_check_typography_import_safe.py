"""Theme token access must not touch QFontDatabase before QApplication."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication


def _assert_no_qapp() -> None:
    assert QApplication.instance() is None, "QApplication already exists"


def _check_theme_without_qapp() -> None:
    _assert_no_qapp()
    from iris.ui.chat.typography import TOKENS

    border = TOKENS.chat_block_border_solid
    assert isinstance(border, str) and border, border
    _assert_no_qapp()


def _check_font_keys_with_qapp() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is QApplication.instance()
    from iris.ui.chat.typography import TOKENS

    size = TOKENS.chat_font_size
    assert isinstance(size, str) and size.endswith("px"), size
    ui = TOKENS.chat_ui_font
    assert isinstance(ui, str) and ui, ui


def main() -> int:
    _check_theme_without_qapp()
    _check_font_keys_with_qapp()
    print("typography_import_safe: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
