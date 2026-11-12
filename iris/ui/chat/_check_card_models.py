"""Card view models. Fence parse and display fields. No HTML."""

from __future__ import annotations

from iris.ui.chat.card_models import RUN_MODES, parse_fence_info, to_code_card, to_shell_card
from iris.ui.chat.chat_blocks import FencedCodeBlock, ToolShellBlock


def main() -> int:
    info = parse_fence_info("python:12:40:iris/ui/chat/chat_blocks.py")
    assert info.language == "python"
    assert info.path == "iris/ui/chat/chat_blocks.py"
    assert info.start_line == 12
    assert info.end_line == 40

    card = to_code_card(FencedCodeBlock("x=1", language="python:iris/foo.py"))
    assert card.header_primary == "foo.py"
    assert "Python" in card.header_secondary
    assert card.copy_payload == "x=1"
    assert "iris/foo.py" in card.open_path

    shell = to_shell_card(
        ToolShellBlock("Shell", "pytest -q", "3 passed", status="ok", block_id="t1")
    )
    assert shell.status_kind == "ok"
    assert shell.status_label == "성공"
    assert shell.show_command_copy
    assert shell.copy_payload == "pytest -q"
    assert shell.phase == "done"

    failed = to_shell_card(
        ToolShellBlock("Shell", "pytest -q", "1 failed", status="error", block_id="t2")
    )
    assert failed.status_kind == "error"
    assert failed.status_label == "실패"
    assert failed.phase == "done"

    assert RUN_MODES == (
        (
            "ask_every_time",
            "Ask Every Time",
            "Ask for permission before running each operation.",
        ),
        (
            "use_allowlist",
            "Allowlist",
            "Automatically run operations after you approve them once.",
        ),
        (
            "run_everything",
            "Run Everything",
            "Automatically run all operations without asking for permission.",
        ),
    )

    print("card_models ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
