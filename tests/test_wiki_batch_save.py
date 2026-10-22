"""여러 PDF 위키 저장. 전부 넣고, 건마다 상태를 알리고, 재첨부는 같은 배치로 남긴다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_import_ops import import_pages, import_progress_label, wiki_batch_notice
from iris.knowledge.wiki_save_intent import (
    followup_wiki_save,
    keep_wiki_batch,
    parse_wiki_save_request,
    reject_attachment_rewrite,
)


class WikiBatchSaveTests(unittest.TestCase):
    def test_save_request_keeps_every_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = []
            for name in ("a.pdf", "b.pdf", "c.pdf"):
                path = root / name
                path.write_bytes(b"%PDF-1.1")
                files.append(str(path))
            request = parse_wiki_save_request("저장안된것들은 저장해줘", files)
            self.assertIsNotNone(request)
            assert request is not None
            self.assertEqual(len(request.sources), 3)
            self.assertEqual(Path(request.sources[0]).name, "a.pdf")
            self.assertEqual(Path(request.sources[2]).name, "c.pdf")
            self.assertEqual(request.source, request.sources[0])

    def test_import_pages_continues_after_one_failure_and_reports_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good_a = root / "a.txt"
            good_b = root / "b.txt"
            good_a.write_text("alpha body", encoding="utf-8")
            good_b.write_text("beta body", encoding="utf-8")
            missing = root / "gone.txt"
            wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
            seen: list[str] = []

            def on_item(index: int, total: int, item: dict) -> None:
                seen.append(import_progress_label(index, total, item))

            result = import_pages(
                wiki,
                [str(good_a), str(missing), str(good_b)],
                on_item=on_item,
            )
            self.assertEqual(result["saved"], 2)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(
                seen,
                [
                    "1/3 저장, a.txt",
                    "2/3 실패, gone.txt",
                    "3/3 저장, b.txt",
                ],
            )
            notice = wiki_batch_notice(result)
            self.assertIn("저장 2건, 실패 1건.", notice)
            self.assertIn("a.txt", notice)
            self.assertIn("b.txt", notice)
            self.assertIn("gone.txt", notice)

    def test_reattach_without_words_stays_on_the_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = []
            for name in ("two.pdf", "three.pdf"):
                path = root / name
                path.write_bytes(b"%PDF-1.1")
                files.append(str(path))
            self.assertIsNone(followup_wiki_save("", files, pending=False))
            again = followup_wiki_save("", files, pending=True, mode="raw")
            self.assertIsNotNone(again)
            assert again is not None
            self.assertEqual(len(again.sources), 2)
            self.assertTrue(again.from_attachment)
            self.assertIsNone(followup_wiki_save("이 파일 설명해줘", files, pending=True))

    def test_status_question_stays_with_the_agent(self) -> None:
        self.assertIsNone(parse_wiki_save_request("내가 전에 pdf를 저장했는지 확인해줘"))
        self.assertFalse(keep_wiki_batch("리니어가 뭐야"))
        self.assertTrue(keep_wiki_batch("pdf 여러개를 줬는데 왜 하나만 있어?"))
        self.assertTrue(keep_wiki_batch(""))

    def test_write_user_note_refuses_attached_documents(self) -> None:
        blocked = reject_attachment_rewrite([r"C:\notes\lecture.pdf"])
        self.assertIn("wiki.import_pages", blocked)
        self.assertIn("write_user_note", blocked)
        self.assertIn("lecture.pdf", blocked)
        self.assertEqual(reject_attachment_rewrite([]), "")
        self.assertEqual(reject_attachment_rewrite([r"C:\notes\photo.png"]), "")


if __name__ == "__main__":
    unittest.main()
