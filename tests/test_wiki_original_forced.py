"""PDF/URL wiki saves must leave an on-disk original beside the note."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_original import (
    first_page_png,
    require_original,
    split_note_view,
    store_original,
    viewer_local_path,
)
from iris.knowledge.wiki_save_intent import parse_wiki_save_request
from iris.ui.wiki_turn import local_document_wiki_save_enabled


def _tiny_pdf(path: Path) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Forced original) Tj ET")
    page[NameObject("/Contents")] = stream
    writer.write(path)


class WikiOriginalForcedTests(unittest.TestCase):
    def test_document_saves_bypass_hermes(self):
        self.assertTrue(local_document_wiki_save_enabled())
        main = Path(__file__).resolve().parents[1] / "iris" / "ui" / "window" / "main_window.py"
        src = main.read_text(encoding="utf-8")
        self.assertIn("documents_only=True", src)

    def test_require_original_copies_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "paper.pdf"
            _tiny_pdf(pdf)
            wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
            path, rel = wiki.write_inbox_note("paper", "## 전체 요약\n\nx\n\n## 핵심 개념\n\ny\n\n## 원본\n\nz\n")
            asset = require_original(path, kind="pdf", source=str(pdf))
            self.assertTrue(asset.endswith("original.pdf"))
            text = path.read_text(encoding="utf-8")
            top, marker = split_note_view(text)
            self.assertEqual(marker, asset)
            self.assertNotIn("## 원본", top)
            self.assertTrue((path.parent / asset).is_file())

    def test_require_original_raises_when_pdf_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
            path, _rel = wiki.write_inbox_note("missing", "body")
            with self.assertRaises(ValueError):
                require_original(path, kind="pdf", source=str(root / "nope.pdf"))

    def test_silent_store_without_require_leaves_gap(self):
        """Regression lock: bare store_original must not be the only call site for docs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "paper.pdf"
            _tiny_pdf(pdf)
            note = root / "note.md"
            note.write_text("# t\n", encoding="utf-8")
            # missing kind still returns empty — callers must use require_original for docs
            self.assertEqual(store_original(note, kind="other", source=str(pdf)), "")

    def test_parse_pdf_attachment_is_document_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "a.pdf"
            _tiny_pdf(pdf)
            req = parse_wiki_save_request("이거 위키에 저장해줘", [str(pdf)])
            self.assertIsNotNone(req)
            self.assertTrue(bool(req.source))
            self.assertTrue(req.from_attachment)

    def test_viewer_stages_non_ascii_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hangul = root / "초파리"
            hangul.mkdir()
            pdf = hangul / "원본.pdf"
            _tiny_pdf(pdf)
            staged = viewer_local_path(pdf)
            self.assertTrue(str(staged).isascii())
            self.assertTrue(staged.is_file())
            self.assertEqual(staged.stat().st_size, pdf.stat().st_size)
            mtime_before = staged.stat().st_mtime
            again = viewer_local_path(pdf)
            self.assertEqual(again, staged)
            self.assertEqual(again.stat().st_mtime, mtime_before)

    def test_first_page_png(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf missing")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "page.pdf"
            doc = pymupdf.open()
            doc.new_page(width=200, height=200)
            doc.save(str(pdf))
            doc.close()
            png = first_page_png(pdf)
            self.assertTrue(png and png[:4] == b"\x89PNG")
            self.assertIsNone(first_page_png(Path(tmp) / "missing.pdf"))

    def test_local_wiki_save_documents_only_skips_answer(self):
        from iris.ui.window.main_window import MainWindow

        turn = MagicMock()
        turn.text = "방금 찾은 내용 위키에 저장해줘"
        turn.attachments = []
        turn.id = "t1"
        window = MagicMock(spec=MainWindow)
        window._history = [
            {"role": "assistant", "content": "# 조사\n\n본문"},
        ]
        window._try_local_wiki_save = MainWindow._try_local_wiki_save.__get__(window, MainWindow)
        window._format_user_turn_content = MagicMock(return_value="x")
        window._active_workspace_iris_panel = MagicMock(return_value=None)
        window._chat = MagicMock()
        window._record_history = MagicMock()
        window._settings = MagicMock(ollama_model="", ollama_base_url="")
        window._saved_model = ""
        window._db = None
        window._model_switch = MagicMock(history_settings=None)
        window._current_project_root = MagicMock(return_value="")
        window._iris_wiki = MagicMock()
        window._finish_current_turn = MagicMock()
        window._present_wiki_import_success = MagicMock()
        window._start_wiki_import_async = MagicMock()

        # documents_only must not intercept answer-only saves
        self.assertFalse(MainWindow._try_local_wiki_save(window, turn, documents_only=True))


if __name__ == "__main__":
    unittest.main()
