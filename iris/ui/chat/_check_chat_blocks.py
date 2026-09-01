"""chat_blocks / chat_renderer 통합 자검 — Cursor식 블록 HTML + 화면별 스모크."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.core.chat_citations import iris_message_to_chat_html
from iris.core.markdown_text import markdown_to_chat_html
from iris.knowledge.iris_wiki import IrisWiki
from iris.ui.chat.chat_blocks import (
    ChatBlockKind,
    FencedCodeBlock,
    ToolShellBlock,
    citation_chip_to_html,
    collapse_anchor_for,
    copy_anchor_for,
    diff_block_to_html,
    file_anchor_for,
    file_chip_to_html,
    fenced_code_to_html,
    marked_tool_shell_to_html,
    parse_copy_anchor,
    parse_file_chip_location,
    parse_iris_file_anchor,
    tool_shell_to_html,
)
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_renderer import (
    render_diff_block,
    render_error_message,
    render_file_chip,
    render_iris_message,
    render_markdown_document,
    render_tool_shell,
    render_user_message,
    render_wiki_document,
)
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisChatLog

_BACKTICK3 = "```"

PROSE_SAMPLE = (
    "**bold** text\n\n"
    "- alpha\n"
    "- beta\n\n"
    "---\n\n"
    "| Col A | Col B |\n"
    "|-------|-------|\n"
    "| 1 | 2 |\n"
)

FENCED_SAMPLE = f"{PROSE_SAMPLE}\n\n{_BACKTICK3}python\nprint('hi')\n{_BACKTICK3}"

WIKI_SAMPLE = (
    "# Demo\n\n"
    "See [Docs](https://docs.example.com/wiki) and https://bare.example.com/x\n\n"
    "![logo](https://cdn.example.com/logo.png)\n\n"
    "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
    f"{_BACKTICK3}python\nprint('wiki')\n{_BACKTICK3}"
)

# offscreen 스모크 — 원격 이미지 prefetch 회피 (렌더 경로는 동일)
WIKI_SMOKE_NOTE = (
    "# Demo\n\n"
    "See [Docs](https://docs.example.com/wiki) and https://bare.example.com/x\n\n"
    "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
    f"{_BACKTICK3}python\nprint('wiki')\n{_BACKTICK3}"
)


def _assert_html_contains(html: str, *needles: str, label: str = "") -> None:
    for needle in needles:
        assert needle in html, f"{label}: missing {needle!r} in {html[:240]!r}"


def _assert_mono_in_html(html: str, *, label: str = "") -> None:
    if "Consolas" in html or "monospace" in html or "Cascadia" in html:
        return
    assert False, f"{label}: no mono font in {html[:240]!r}"


def _assert_tokens() -> None:
    t = TOKENS
    assert t.chat_block_radius == 8
    assert "Consolas" in t.chat_block_mono_font

    from iris.core.activity_privacy import prepare_chat_text

    fenced = f"{_BACKTICK3}python\nx=1\n{_BACKTICK3}"
    assert fenced in prepare_chat_text(f"before\n{fenced}\nafter"), "prepare_chat_text must keep markdown fences"


def _assert_prose() -> None:
    html_out = render_iris_message(PROSE_SAMPLE)
    _assert_html_contains(
        html_out,
        "<strong>bold</strong>",
        "<ul",
        "alpha",
        "border-top:1px solid",
        "<table",
        "1",
        label="prose",
    )


def _assert_fenced_code() -> None:
    t = TOKENS
    block = FencedCodeBlock("print('hi')", language="python")
    fenced = fenced_code_to_html(block)
    _assert_html_contains(
        fenced,
        f"border-radius:{t.chat_block_radius}px",
        t.chat_block_mono_font,
        "python",
        "print(",
        "복사",
        "iris-copy://",
        label="fenced_code_to_html",
    )
    assert parse_copy_anchor(copy_anchor_for("print('hi')")) == "print('hi')"

    md = render_iris_message(FENCED_SAMPLE)
    _assert_html_contains(
        md,
        "python",
        "iris-copy://",
        t.chat_block_mono_font,
        "print(",
        label="render_iris_message fenced",
    )


def _assert_tool_shell() -> None:
    t = TOKENS
    shell = tool_shell_to_html(
        ToolShellBlock("Run tests", "pytest -q", "3 passed", status="ok", block_id="t1")
    )
    _assert_html_contains(
        shell,
        f"border-radius:{t.chat_block_radius}px",
        t.chat_block_mono_font,
        "Run tests",
        "pytest -q",
        "&gt;_",
        collapse_anchor_for("t1"),
        "▼",
        label="tool_shell ok",
    )

    err_shell = tool_shell_to_html(
        ToolShellBlock("Deploy", "npm run deploy", "exit 1", status="error", block_id="t2")
    )
    _assert_html_contains(err_shell, t.error, "Deploy", label="tool_shell error")

    marked = marked_tool_shell_to_html(
        ToolShellBlock("Build", "npm run build", "done", status="ok", block_id="t3")
    )
    _assert_html_contains(marked, "IRIS_TOOL_t3_START", "IRIS_TOOL_t3_END", label="tool markers")

    tool_api = render_tool_shell("Build", "npm run build", "done", "ok", "t4")
    _assert_html_contains(
        tool_api,
        "Build",
        f"border-radius:{t.chat_block_radius}px",
        "iris-collapse://t4",
        "&gt;_",
        label="render_tool_shell",
    )


def _assert_error_and_user() -> None:
    t = TOKENS
    err = render_error_message("something failed")
    _assert_html_contains(err, "something failed", f"border-radius:{t.chat_block_radius}px", label="error")

    user = render_user_message("**hello** world")
    _assert_html_contains(user, "<strong>hello</strong>", label="user bold")

    chip = citation_chip_to_html(1, "https://example.com", "Example")
    _assert_html_contains(chip, 'href="https://example.com"', "[1]", label="citation chip")

    md = markdown_to_chat_html("**bold** and `code`\n\n```py\nx=1\n```")
    _assert_html_contains(md, "bold", f"border-radius:{t.chat_block_radius}px", "iris-copy://", label="markdown_to_chat_html")

    iris = iris_message_to_chat_html(
        "See [Docs](https://docs.example.com/a) and https://bare.example.com/x"
    )
    _assert_html_contains(iris, "SOURCES", "docs.example.com", label="iris citations")

    assert render_markdown_document("", citations=False) == ""
    assert ChatBlockKind.FENCED_CODE.value == "fenced_code"
    assert ChatBlockKind.FILE_CHIP.value == "file_chip"
    assert ChatBlockKind.DIFF.value == "diff"


def _assert_file_chips_and_diff() -> None:
    t = TOKENS
    enabled = file_chip_to_html("iris/ui/chat/chat_blocks.py", enabled=True)
    disabled = file_chip_to_html("iris/ui/chat/chat_blocks.py", enabled=False)
    _assert_html_contains(
        enabled,
        "iris-file://",
        "iris/ui/chat/chat_blocks.py",
        t.chat_block_mono_font,
        label="file chip enabled",
    )
    assert "iris-file://" not in disabled
    _assert_html_contains(disabled, t.disabled, label="file chip disabled")
    assert parse_iris_file_anchor(file_anchor_for("src/main.py:2:3")) == "src/main.py:2:3"
    path, line, col = parse_file_chip_location("src/main.py:2:3")
    assert path == "src/main.py" and line == 2 and col == 3

    diff = diff_block_to_html("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
    _assert_html_contains(diff, t.success, t.error, ">diff</span>", label="diff block")
    _assert_mono_in_html(diff, label="diff block mono")

    chip = render_file_chip("iris/ui/chat/chat_renderer.py")
    assert "iris/ui/chat/chat_renderer.py" in chip
    md = render_iris_message(
        "fix `iris/ui/chat/chat_blocks.py` and iris/ui/chat/chat_renderer.py"
    )
    assert "iris/ui/chat/chat_blocks.py" in md
    assert "iris-file://" in md or t.disabled in md

    diff_md = render_diff_block("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
    _assert_html_contains(diff_md, t.success, t.error, label="render_diff_block")
    fenced = render_iris_message(
        "```diff\n--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-old\n+new\n```"
    )
    _assert_html_contains(fenced, t.success, t.error, label="render_iris_message diff fence")


def _assert_wiki_document() -> None:
    t = TOKENS
    wiki_html = render_wiki_document(WIKI_SAMPLE)
    _assert_html_contains(
        wiki_html,
        "SOURCES",
        "docs.example.com",
        "iris-image:",
        "cdn.example.com/logo.png",
        "print(",
        f"border-radius:{t.chat_block_radius}px",
        "iris-copy://",
        "<pre",
        label="wiki document",
    )
    assert "iris-tts://" not in wiki_html


def _smoke_chat_panel(app: QApplication) -> None:
    panel = ChatPanel()
    panel.show()
    app.processEvents()
    panel.append_message_instant("You", "**user** sample")
    panel.append_message_instant("Iris", FENCED_SAMPLE)
    panel.insert_tool_block(
        title="Smoke shell",
        command="echo ok",
        output="ok",
        status="ok",
        block_id="smoke-tool",
    )
    app.processEvents()
    html_doc = panel._log.toHtml()
    _assert_html_contains(
        html_doc,
        "font-weight:700",
        "user",
        "python",
        "iris-copy://",
        "Smoke shell",
        "iris-collapse://smoke-tool",
        label="ChatPanel smoke",
    )
    _assert_mono_in_html(html_doc, label="ChatPanel smoke")
    assert "iris-tts://" in html_doc


def _smoke_workspace_log(app: QApplication) -> None:
    log = WorkspaceIrisChatLog("SmokeWsLog")
    log.show()
    app.processEvents()
    log.append_user("**workspace** question")
    log.append_iris_chunk("partial…")
    log.end_iris(FENCED_SAMPLE)
    app.processEvents()
    html_doc = log.toHtml()
    _assert_html_contains(
        html_doc,
        "font-weight:700",
        "workspace",
        "python",
        "iris-copy://",
        "print(",
        label="WorkspaceIrisChatLog smoke",
    )
    _assert_mono_in_html(html_doc, label="WorkspaceIrisChatLog smoke")
    assert "iris-tts://" not in html_doc


def _smoke_obsidian_wiki(app: QApplication) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        _path, rel = wiki.write_inbox_note("Render QA", WIKI_SMOKE_NOTE)
        page = ObsidianWorkspacePage()
        page.show()
        page.set_wiki(wiki)
        page.show_note(rel)
        app.processEvents()
        html_doc = page._body.toHtml()
        _assert_html_contains(
            html_doc,
            "python",
            "iris-copy://",
            "print(",
            "docs.example.com",
            label="ObsidianWorkspacePage smoke",
        )
        _assert_mono_in_html(html_doc, label="ObsidianWorkspacePage smoke")
        assert "iris-tts://" not in html_doc


def main() -> int:
    _assert_tokens()
    _assert_prose()
    _assert_fenced_code()
    _assert_tool_shell()
    _assert_error_and_user()
    _assert_file_chips_and_diff()
    _assert_wiki_document()

    app = QApplication.instance() or QApplication(sys.argv)
    _smoke_chat_panel(app)
    _smoke_workspace_log(app)
    _smoke_obsidian_wiki(app)

    print("chat_blocks ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
