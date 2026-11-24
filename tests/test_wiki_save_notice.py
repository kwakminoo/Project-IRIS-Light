"""위키 저장 안내 — 화면 이동 없이 클릭 경로만 남긴다."""

from __future__ import annotations

from unittest import TestCase

from PyQt6.QtWidgets import QApplication

from iris.knowledge.wiki_import_ops import wiki_location_label, wiki_save_notice
from iris.ui.chat.chat_blocks import parse_iris_wiki_anchor, wiki_anchor_for
from iris.ui.chat.chat_renderer import render_iris_message

_APP = QApplication.instance() or QApplication([])


class WikiSaveNoticeTests(TestCase):
    def test_notice_keeps_place_and_links_the_saved_note(self) -> None:
        rel = "user/inbox/pdf-export.md"
        notice = wiki_save_notice(
            {"rel_path": rel, "title": "PDF 저장", "truncated": False},
            project="IRIS",
            href=wiki_anchor_for(rel),
        )
        self.assertTrue(notice.startswith("저장되었습니다."))
        self.assertIn("저장 위치:", notice)
        self.assertIn("Wiki > IRIS > PDF 저장", notice)
        self.assertNotIn("Wiki 화면에서", notice)
        href = wiki_anchor_for(rel)
        self.assertIn(href, notice)
        self.assertEqual(parse_iris_wiki_anchor(href), rel)
        html = render_iris_message(notice)
        self.assertIn("iris-wiki://", html)
        self.assertIn("PDF 저장", html)

    def test_inbox_without_project_uses_the_folder(self) -> None:
        self.assertEqual(
            wiki_location_label("user/inbox/note.md", "메모"),
            "Wiki > inbox > 메모",
        )
