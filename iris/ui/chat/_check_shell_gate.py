"""Shell wait, auto-run, and Apply write. No user approval file."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from iris.ui.chat.card_html import code_card_to_html
from iris.ui.chat.card_models import CodeCardModel
from iris.ui.chat.chat_blocks import (
    ToolShellBlock,
    apply_code_to_root,
    handle_apply_click,
    handle_shell_approval_click,
    marked_tool_shell_to_html,
    parse_apply_anchor,
    parse_apply_target,
)
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_renderer import render_tool_shell
from iris.ui.chat.shell_approval import ApprovalState, choose, preview_command, should_auto_run
from iris.ui.chat.shell_gate import arm, decide, gate_project_run, take


class _Chat:
    def __init__(self) -> None:
        self.inserts: list[dict] = []
        self.replacements: list[tuple[str, dict]] = []

    def insert_tool_block(self, **kwargs) -> str:
        self.inserts.append(kwargs)
        return "block-1"

    def replace_tool_block(self, block_id: str, **kwargs) -> bool:
        self.replacements.append((block_id, kwargs))
        return True


def _boom(_block_id: str) -> str:
    raise AssertionError("waited")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is QApplication.instance()

    assert should_auto_run(ApprovalState(), "git status") is False
    assert should_auto_run(ApprovalState(mode_id="run_everything"), "git status") is True
    allowed = ApprovalState(mode_id="use_allowlist", allowlist=("git",))
    assert should_auto_run(allowed, "git status") is True
    assert should_auto_run(ApprovalState(mode_id="use_allowlist", allowlist=("npm",)), "git status") is False
    assert should_auto_run(allowed, "") is False
    assert should_auto_run(allowed, "   ") is False

    # Always Run: switch ask_every_time → use_allowlist and remember prefix.
    alwaysed = choose(ApprovalState(), "always", "git status")
    assert alwaysed.mode_id == "use_allowlist"
    assert "git" in alwaysed.allowlist
    assert should_auto_run(alwaysed, "git status") is True
    # Empty prefix is a no-op; existing allowlist entries stay when adding another.
    assert choose(ApprovalState(), "always", "   ") == ApprovalState()
    again = choose(alwaysed, "always", "npm test")
    assert again.mode_id == "use_allowlist"
    assert again.allowlist == ("git", "npm")
    # Idempotent: same prefix already listed still lands on use_allowlist.
    stuck = ApprovalState(mode_id="ask_every_time", allowlist=("git",))
    unstuck = choose(stuck, "always", "git status")
    assert unstuck.mode_id == "use_allowlist"
    assert unstuck.allowlist == ("git",)
    assert should_auto_run(unstuck, "git status") is True

    assert preview_command({"command": " git status "}) == "git status"
    assert preview_command({"file": "main.py"}) == "main.py"
    assert preview_command({"path": "src/a.py"}) == "src/a.py"
    assert preview_command({}) == "project.run"

    from iris.ui.chat.shell_gate import try_card_confirm

    card_chat = _Chat()
    attention: list[int] = []
    decided = try_card_confirm(
        chat=card_chat,
        command="git status",
        title="Shell",
        approval=ApprovalState(),
        wait=lambda _bid: "run",
        on_attention=lambda: attention.append(1),
    )
    assert decided.approved is True
    assert decided.block_id == "block-1"
    assert len(card_chat.inserts) == 1
    assert attention == [1]
    assert (
        try_card_confirm(
            chat=None,
            command="git status",
            title="Shell",
            approval=ApprovalState(),
            wait=_boom,
            on_attention=lambda: attention.append(1),
        ).approved
        is None
    )
    assert attention == [1]

    attention.clear()
    auto_attn = try_card_confirm(
        chat=_Chat(),
        command="git status",
        title="Shell",
        approval=ApprovalState(mode_id="run_everything"),
        wait=_boom,
        on_attention=lambda: attention.append(1),
    )
    assert auto_attn.approved is True
    assert attention == []

    class _EmptyInsert:
        def insert_tool_block(self, **_kwargs) -> str:
            return ""

    attention.clear()
    empty_insert = try_card_confirm(
        chat=_EmptyInsert(),
        command="git status",
        title="Shell",
        approval=ApprovalState(),
        wait=_boom,
        on_attention=lambda: attention.append(1),
    )
    assert empty_insert.approved is None
    assert attention == []

    arm("gate-run")
    found: list[str] = []

    def _wait_for_run() -> None:
        found.append(take("gate-run"))

    waiter = threading.Thread(target=_wait_for_run, daemon=True)
    waiter.start()
    decide("gate-run", "run")
    waiter.join(2)
    assert found == ["run"], found
    assert not waiter.is_alive()
    decide("missing-id", "run")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        written = apply_code_to_root(root, "hello.py", "hello\n")
        assert written == (root / "hello.py").resolve()
        assert written is not None and written.read_text(encoding="utf-8") == "hello\n"
        assert apply_code_to_root(root, "../escape.py", "nope") is None
        assert not (root.parent / "escape.py").exists()
        abs_target = Path("C:/abs.py")
        existed = abs_target.exists()
        assert apply_code_to_root(root, "C:/abs.py", "nope") is None
        if not existed:
            assert not abs_target.exists()
        assert apply_code_to_root(root, "hello.py", "") is None

    def _action(args: dict) -> dict:
        calls.append(args)
        return {"ok": True, "action": "project.run", "result": {"summary": "ran", "command": "git status"}}

    calls: list[dict] = []
    gate_attn: list[int] = []
    skipped_chat = _Chat()
    skipped = gate_project_run(
        {"command": "git status"},
        _action,
        chat=skipped_chat,
        on_ui_thread=False,
        approval=ApprovalState(),
        wait=lambda _block_id: "skip",
        on_attention=lambda: gate_attn.append(1),
    )
    assert len(skipped_chat.inserts) == 1
    assert skipped_chat.inserts[0]["phase"] == "pending"
    assert skipped_chat.inserts[0]["command"] == "git status"
    assert calls == []
    assert skipped["ok"] is False
    assert skipped["action"] == "project.run"
    assert skipped["error"] == "skipped"
    assert skipped["result"] == {"summary": "Skipped"}
    assert skipped_chat.replacements == []
    assert gate_attn == [1]

    calls.clear()
    ran_chat = _Chat()
    ran = gate_project_run(
        {"command": "git status"},
        _action,
        chat=ran_chat,
        on_ui_thread=False,
        approval=ApprovalState(),
        wait=lambda _block_id: "run",
        on_attention=lambda: gate_attn.append(1),
    )
    assert len(ran_chat.inserts) == 1
    assert ran_chat.inserts[0]["phase"] == "pending"
    assert calls == [{"command": "git status"}]
    assert ran["ok"] is True
    assert ran_chat.replacements and ran_chat.replacements[0][0] == "block-1"
    assert ran_chat.replacements[0][1]["phase"] == "done"
    assert gate_attn == [1, 1]

    calls.clear()
    gate_attn.clear()
    quiet = _Chat()
    gate_project_run(
        {"command": "git status"},
        _action,
        chat=quiet,
        on_ui_thread=False,
        approval=ApprovalState(mode_id="run_everything"),
        wait=_boom,
        on_attention=lambda: gate_attn.append(1),
    )
    assert calls == [{"command": "git status"}]
    assert len(quiet.inserts) == 1
    assert quiet.inserts[0].get("phase", "done") != "pending"
    assert gate_attn == []

    calls.clear()
    gate_project_run(
        {"command": "git status"},
        _action,
        chat=None,
        on_ui_thread=False,
        approval=ApprovalState(),
        wait=_boom,
    )
    assert calls == [{"command": "git status"}]

    calls.clear()
    asking = _Chat()
    gate_project_run(
        {"command": "git status"},
        _action,
        chat=asking,
        on_ui_thread=True,
        approval=ApprovalState(),
        wait=_boom,
    )
    assert calls == [{"command": "git status"}]
    assert len(asking.inserts) == 1
    assert asking.inserts[0].get("phase", "done") != "pending"

    pending_html = render_tool_shell("Shell", "git status", "", "ok", "bid", phase="pending")
    assert "iris-run://bid" in pending_html
    done_html = render_tool_shell("Shell", "git status", "", "ok", "bid")
    assert "iris-run://bid" not in done_html
    running_html = render_tool_shell(
        "Shell", "git status", "partial out", "ok", "bid", phase="running"
    )
    assert "iris-run://" not in running_html
    assert "iris-skip://" not in running_html
    assert "partial out" in running_html
    assert "실행 중" in running_html

    panel = ChatPanel()
    stored_id = panel.insert_tool_block(
        title="Shell",
        command="git status",
        output="",
        status="ok",
        phase="pending",
    )
    stored = panel._tool_blocks[stored_id]
    assert stored.phase == "pending"
    assert "iris-run://" in marked_tool_shell_to_html(stored)

    card_html = code_card_to_html(
        CodeCardModel(
            body="print(1)\n",
            lang_id="python",
            header_primary="my file.py",
            header_secondary="Python",
            copy_payload="print(1)\n",
            open_path="dir/my file.py",
        )
    )
    assert "iris-apply://dir%2Fmy%20file.py" in card_html
    href = re.search(r'href="(iris-apply://[^"]+)"', card_html)
    assert href is not None
    assert parse_apply_target(href.group(1)) == ("dir/my file.py", "print(1)\n")
    assert parse_apply_anchor("iris-apply://dir%2Fmy%20file.py") == "dir/my file.py"
    assert parse_apply_target("iris-apply://dir%2Fmy%20file.py") == ("dir/my file.py", "")

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "clicks.json"
        edit = QTextEdit()
        pending = ToolShellBlock(
            "Shell",
            "git status",
            "",
            status="ok",
            block_id="tool9",
            phase="pending",
        )
        blocks = {"tool9": pending}
        arm("tool9")
        clicked: list[str] = []
        click_waiter = threading.Thread(target=lambda: clicked.append(take("tool9")), daemon=True)
        click_waiter.start()
        assert handle_shell_approval_click(edit, blocks, "iris-run://tool9", approval_path=store)
        click_waiter.join(2)
        assert clicked == ["run"], clicked
        assert blocks["tool9"].phase == "pending"
        assert not store.exists()

        skipped_block = ToolShellBlock(
            "Shell",
            "git status",
            "",
            status="ok",
            block_id="tool8",
            phase="pending",
        )
        edit.setHtml(marked_tool_shell_to_html(skipped_block))
        arm("tool8")
        assert handle_shell_approval_click(
            edit, {"tool8": skipped_block}, "iris-skip://tool8", approval_path=store
        )
        assert take("tool8") == "skip"
        assert not store.exists()

        handle_apply_click(edit, "iris-apply://hello.py")

    print("shell_gate ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
