"""Shell approval choice. Record the click. Do not run the command."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from iris.ui.chat.card_models import RUN_MODES, to_shell_card
from iris.ui.chat.chat_blocks import (
    ToolShellBlock,
    build_run_mode_menu,
    handle_shell_approval_click,
    marked_tool_shell_to_html,
    parse_apply_anchor,
    tool_shell_to_html,
    wire_run_mode_menu,
)
from iris.ui.chat.chat_renderer import _chat_url_ok
from iris.ui.chat.shell_approval import ApprovalState, choose, command_prefix, load, save


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is QApplication.instance()

    assert command_prefix("") == ""
    assert command_prefix("git status") == "git"
    assert command_prefix('"git" status') == "git"

    once = choose(ApprovalState(), "always", "git status")
    twice = choose(once, "always", "git status")
    assert once.mode_id == "ask_every_time"
    assert once.allowlist == ("git",)
    assert twice.allowlist == ("git",)

    base = ApprovalState(mode_id="ask_every_time", allowlist=("git",))
    for mode_id, _label, _description in RUN_MODES:
        picked = choose(base, mode_id, "git status")
        assert picked.mode_id == mode_id
        assert picked.allowlist == ("git",)
    assert choose(base, "run", "git status") == base
    assert choose(base, "skip", "git status") == base
    assert choose(base, "nope", "git status") == base

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shell_approval.json"
        save(ApprovalState(mode_id="use_allowlist", allowlist=("git", "npm")), path)
        save(ApprovalState(mode_id="use_allowlist", allowlist=("git", "npm")), path)
        loaded = load(path)
        assert loaded.mode_id == "use_allowlist"
        assert loaded.allowlist == ("git", "npm")
        path.write_text("{not json", encoding="utf-8")
        assert load(path) == ApprovalState()

        pending = ToolShellBlock(
            "List files",
            "git status",
            "",
            status="ok",
            block_id="tool1",
            phase="pending",
        )
        pending_html = tool_shell_to_html(pending)
        assert "iris-run://tool1" in pending_html
        assert "Ask Every Time" not in pending_html
        assert to_shell_card(pending).phase == "pending"

        edit = QTextEdit()
        edit.setHtml(marked_tool_shell_to_html(pending))
        blocks = {"tool1": pending}
        store = Path(tmp) / "clicks.json"
        assert handle_shell_approval_click(
            edit, blocks, "iris-run://tool1", approval_path=store
        )
        assert blocks["tool1"].phase == "pending"
        assert not store.exists()
        assert handle_shell_approval_click(
            edit, blocks, "iris-always://tool1", approval_path=store
        )
        assert blocks["tool1"].phase == "pending"
        assert load(store).allowlist == ("git",)
        assert handle_shell_approval_click(
            edit, blocks, "iris-skip://tool1", approval_path=store
        )
        skipped = blocks["tool1"]
        assert skipped.phase == "done"
        assert skipped.status == "skipped"
        skipped_html = edit.toHtml()
        assert "Skipped" in skipped_html
        assert "iris-run://" not in skipped_html
        assert load(store).allowlist == ("git",)

        assert handle_shell_approval_click(edit, {}, "iris-mode://missing") is False
        assert parse_apply_anchor("iris-apply://dir%2Fmy%20file.py") == "dir/my file.py"
        assert not (Path(tmp) / "dir" / "my file.py").exists()

    assert _chat_url_ok("iris-run://tool1")
    assert _chat_url_ok("iris-always://tool1")
    assert _chat_url_ok("iris-skip://tool1")
    assert _chat_url_ok("iris-mode://tool1")
    assert _chat_url_ok("iris-apply://dir%2Fmy%20file.py")

    menu_parent = QTextEdit()
    menu = build_run_mode_menu(menu_parent)
    labels = [action.text() for action in menu.actions()]
    tips = [action.toolTip() for action in menu.actions()]
    assert labels == [label for _mode_id, label, _description in RUN_MODES]
    assert tips == [description for _mode_id, _label, description in RUN_MODES]
    assert len(labels) == 3
    with tempfile.TemporaryDirectory() as tmp:
        mode_path = Path(tmp) / "mode.json"
        wire_run_mode_menu(menu, mode_path)
        menu.actions()[2].trigger()
        assert load(mode_path).mode_id == "run_everything"
        assert load(mode_path).allowlist == ()

    print("run_approval ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
