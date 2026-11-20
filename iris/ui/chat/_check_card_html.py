"""Card HTML painters. Models in, table and pre markup out."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.card_html import code_card_to_html, shell_card_to_html
from iris.ui.chat.card_models import RUN_MODES, CodeCardModel, ShellCardModel, to_code_card, to_shell_card
from iris.ui.chat.chat_blocks import (
    FencedCodeBlock,
    ToolShellBlock,
    fenced_code_from_info,
    fenced_code_to_html,
)

_CODE = "ALPHA_CARD_TOKEN = 1"


def main() -> int:
    # typography defaults read Qt fonts. Dropping this reference is 0xC0000409.
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is QApplication.instance()
    path_html = code_card_to_html(
        to_code_card(
            FencedCodeBlock(
                _CODE,
                language="python:iris/ui/chat/chat_blocks.py",
            )
        )
    )
    for needle in (
        "chat_blocks.py",
        "Python",
        "열기",
        "iris-file://",
        "복사",
        "ALPHA_CARD_TOKEN",
    ):
        assert needle in path_html, needle

    lang_html = code_card_to_html(
        to_code_card(FencedCodeBlock(_CODE, language="python"))
    )
    assert "복사" in lang_html
    assert "iris-file://" not in lang_html

    ok_html = shell_card_to_html(
        to_shell_card(
            ToolShellBlock("Run tests", "pytest -q", "3 passed", status="ok", block_id="t1")
        )
    )
    assert "성공" in ok_html
    assert "명령 복사" in ok_html
    assert "pytest -q" in ok_html

    err_html = shell_card_to_html(
        to_shell_card(
            ToolShellBlock("Deploy", "npm run deploy", "exit 1", status="error", block_id="t2")
        )
    )
    assert "실패" in err_html

    hidden = "HIDDEN_SHELL_OUTPUT"
    collapsed_html = shell_card_to_html(
        to_shell_card(
            ToolShellBlock(
                "Run tests",
                "pytest -q",
                hidden,
                status="ok",
                block_id="t3",
                collapsed=True,
            )
        )
    )
    assert hidden in collapsed_html
    assert "display:none" in collapsed_html

    ranged = fenced_code_to_html(fenced_code_from_info("python:12:40:iris/foo.py", "y=2"))
    assert "iris/foo.py:12-40" in ranged, ranged
    assert "열기" in ranged

    assert "Apply" in path_html
    assert "iris-apply://iris%2Fui%2Fchat%2Fchat_blocks.py" in path_html
    assert "Apply" not in lang_html

    spaced = code_card_to_html(
        CodeCardModel(
            body="x = 1",
            lang_id="python",
            header_primary="my file.py",
            header_secondary="Python",
            copy_payload="x = 1",
            open_path="dir/my file.py",
        )
    )
    assert "Apply" in spaced
    assert "iris-apply://dir%2Fmy%20file.py" in spaced

    pending_fields = dict(
        title="List files",
        command="echo hi",
        output="",
        status_kind="ok",
        status_label="성공",
        block_id="pend1",
        collapsed=True,
        show_command_copy=False,
        copy_payload="",
    )
    pending_html = shell_card_to_html(ShellCardModel(**pending_fields, phase="pending"))
    assert ">Run</a>" in pending_html
    assert ">Always Run</a>" in pending_html
    assert ">Skip</a>" in pending_html
    assert "▼" in pending_html
    for scheme in ("iris-run://", "iris-always://", "iris-skip://", "iris-mode://"):
        assert f"{scheme}pend1" in pending_html, scheme
    for _mode_id, label, _description in RUN_MODES:
        assert label not in pending_html, label
    assert "Apply" not in pending_html

    done_html = shell_card_to_html(ShellCardModel(**pending_fields))
    for absent in ("Run", "Always Run", "Skip", "iris-mode://"):
        assert absent not in done_html, absent
    done_from_block = shell_card_to_html(
        to_shell_card(
            ToolShellBlock("List files", "echo hi", "", status="ok", block_id="pend1")
        )
    )
    for absent in ("Run", "Always Run", "Skip", "iris-mode://"):
        assert absent not in done_from_block, absent

    print("card_html ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
