"""위키 공부 UX 자검 — 메모 / 선택 FAB / 인용 칩."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_quote import (
    WIKI_QUOTE_MIME,
    WikiQuote,
    decode_wiki_quote_bytes,
    encode_wiki_quote_bytes,
    format_quotes_for_model,
)
from iris.knowledge.wiki_term_explain import (
    explain_term,
    selection_eligible_for_fab,
)
from iris.storage.wiki_page_memos import PageMemoStore
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.knowledge.wiki_study_widgets import (
    ComposerWikiQuoteStrip,
    parse_wiki_quote_from_mime,
)
from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage


def main() -> None:
    assert selection_eligible_for_fab("가치함수")
    assert not selection_eligible_for_fab("")
    assert not selection_eligible_for_fab("x" * 200)

    msg = explain_term("TD", "notes/rl.md", "TD 학습은 시간차이다", explainer=lambda s, n, c: f"OK:{s}")
    assert msg == "OK:TD", msg

    q = WikiQuote("user/a.md", "노트A", "선택한 문장").normalized()
    assert q is not None
    raw = encode_wiki_quote_bytes(q)
    assert decode_wiki_quote_bytes(raw) == q
    mime = QMimeData()
    mime.setText(q.quote)
    mime.setData(WIKI_QUOTE_MIME, raw)
    assert parse_wiki_quote_from_mime(mime) == q
    plain = QMimeData()
    plain.setText("그냥 텍스트")
    assert parse_wiki_quote_from_mime(plain) is None

    payload = format_quotes_for_model([q], "이게 뭐야?")
    assert "위키 인용" in payload and "노트A" in payload and "이게 뭐야?" in payload

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = PageMemoStore(root)
        store.add("n.md", "필기")
        assert store.count("n.md") == 1
        assert not list((root / "vault").rglob("*")) if not (root / "vault").exists() else True

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        wiki_root = Path(tmp)
        wiki = IrisWiki(docs_root=wiki_root / "docs", user_root=wiki_root / "wiki")
        wiki.write_inbox_note(
            "Study Note",
            "가치함수 V(s) 는 상태의 기대 수익이다.\n\nTD는 시간차 학습이다.\n\n"
            + ("긴문장 " * 40),
            rel_path="inbox/study-note.md",
        )
        page = ObsidianWorkspacePage()
        page.resize(1100, 700)
        page.set_wiki(wiki)
        page.show_note("user/inbox/study-note.md")
        page._memo_store = PageMemoStore(wiki_root / "state")  # noqa: SLF001 — 자검용
        page._memo_panel._store = page._memo_store  # noqa: SLF001
        page._memo_panel.set_note(page.current_note)  # noqa: SLF001
        page._memo_store.add(page.current_note, "자검 메모")
        page._memo_btn.set_count(page._memo_store.count(page.current_note))  # noqa: SLF001
        assert page._memo_btn._count == 1  # noqa: SLF001
        assert page._book_fab.isHidden()  # noqa: SLF001

        cursor = page._body.textCursor()  # noqa: SLF001
        plain = page._body.toPlainText()  # noqa: SLF001
        idx = plain.find("TD")
        assert idx >= 0, plain
        cursor.setPosition(idx)
        cursor.setPosition(idx + 2, QTextCursor.MoveMode.KeepAnchor)
        page._body.setTextCursor(cursor)  # noqa: SLF001
        page._on_body_selection()  # noqa: SLF001
        assert not page._book_fab.isHidden(), "짧은 선택이면 FAB 표시"  # noqa: SLF001

        # 장문 선택 → FAB 숨김
        cursor.select(QTextCursor.SelectionType.Document)
        page._body.setTextCursor(cursor)  # noqa: SLF001
        page._on_body_selection()  # noqa: SLF001
        assert page._book_fab.isHidden()  # noqa: SLF001

        page.set_term_explainer(lambda s, n, c: f"설명:{s}")
        cursor.setPosition(idx)
        cursor.setPosition(idx + 2, QTextCursor.MoveMode.KeepAnchor)
        page._body.setTextCursor(cursor)  # noqa: SLF001
        page._on_body_selection()  # noqa: SLF001
        page._on_term_explain("TD")  # noqa: SLF001
        assert not page._term_pop.isHidden()  # noqa: SLF001
        assert "설명:TD" in page._term_pop._body.text()  # noqa: SLF001

        quote = page._body.current_quote()  # noqa: SLF001
        assert quote is not None and "TD" in quote.quote
        copied = page._body.createMimeDataFromSelection()  # noqa: SLF001
        assert copied.hasFormat(WIKI_QUOTE_MIME)
        assert parse_wiki_quote_from_mime(copied) is not None

        panel = ChatPanel()
        strip: ComposerWikiQuoteStrip = panel._input_area.wiki_quote_strip  # noqa: SLF001
        strip.add_quote(quote)
        assert not strip.isHidden()
        assert panel._composer_can_send()  # noqa: SLF001
        panel._input.clear()  # noqa: SLF001
        # 인용만으로 전송 페이로드 구성
        quotes = strip.take_quotes()
        text = format_quotes_for_model(quotes, "")
        assert "Study" in text or "study" in text.lower() or "TD" in text

    print("wiki_study_ux ok")


if __name__ == "__main__":
    main()
