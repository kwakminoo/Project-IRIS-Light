"""Selective folder retrieval, capability boundaries, and chat isolation."""
import tempfile
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.runtime.attachment_context import prepare_attachments, MAX_CONTEXT_CHARS
from iris.runtime.attachment_store import AttachmentStore
from tests.test_attachment_pipeline import create_fixtures


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.files = create_fixtures(self.root)
        self.folder = self.root / "project"
        (self.folder / "src").mkdir(parents=True)
        (self.folder / "docs").mkdir()
        (self.folder / "README.md").write_text("PROJECT_CODE=FOLDER-777", encoding="utf-8")
        (self.folder / "src/config.py").write_text('PROJECT_NAME="IRIS_FOLDER_TEST"\nworkspaceRoot = "test"', encoding="utf-8")
        (self.folder / "docs/guide.md").write_text("Guide", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_folder_selects_late_file_without_extracting_everything(self):
        for i in range(80):
            (self.folder / f"a{i:03}.txt").write_text("unrelated" * 1000, encoding="utf-8")
        store = AttachmentStore()
        store.attach([str(self.folder)])
        with patch("iris.runtime.attachment_store._read", wraps=__import__("iris.runtime.attachment_context", fromlist=["_read"])._read) as reader:
            result = store.prepare("src/config.py PROJECT_NAME 값을 알려줘")
        self.assertLess(reader.call_count, 7)
        self.assertIn("IRIS_FOLDER_TEST", result.model_content("read"))
        self.assertLessEqual(sum(len(a.text) for a in result.attachments), MAX_CONTEXT_CHARS)
        self.assertIn("docs/guide.md", store.prepare("폴더 구조").model_content("read"))

    def test_search_metadata_and_scoped_tools(self):
        store = AttachmentStore()
        store.attach([str(self.folder)])
        aid = next(iter(store.roots))
        hits = store.search_attached_files("workspaceRoot")
        self.assertEqual(hits[0]["relative_path"], "src/config.py")
        self.assertEqual(hits[0]["snippets"][0]["line"], 2)
        self.assertEqual(len(store.search_attached_files("", extension="py")), 1)
        self.assertEqual(len(store.list_attached_directory(aid, "src")), 1)
        self.assertIn("FOLDER-777", store.read_file_chunk(aid, "README.md"))
        for relative in ["../test.txt", str(self.files["txt"]), "src/../../test.txt", "C:/test.txt", "src/config.py:stream"]:
            with self.subTest(path=relative), self.assertRaises(ValueError):
                store.read_attached_file(aid, relative)
        metadata = store.list_attached_files()[0]
        for key in ["full_path", "relative_path", "extension", "mime_type", "size", "modified_time", "attachment_id", "folder_root", "extracted_text"]:
            self.assertIn(key, metadata)

    def test_exclusions_custom_patterns_and_no_reads_at_index_time(self):
        for name in [".git", "out", "target", "coverage", ".next", ".cache", "generated"]:
            (self.folder / name).mkdir()
            (self.folder / name / "secret.txt").write_text("secret", encoding="utf-8")
        store = AttachmentStore(exclude_patterns=["generated"])
        with patch("iris.runtime.attachment_store._read", side_effect=AssertionError("eager extraction")):
            store.attach([str(self.folder)])
        self.assertEqual(len(store.list_attached_files()), 3)

    def test_mixed_multiple_and_followup(self):
        a, b = self.root / "a.txt", self.root / "b.txt"
        a.write_text("AAA-111", encoding="utf-8")
        b.write_text("BBB-222", encoding="utf-8")
        store = AttachmentStore()
        result = prepare_attachments([str(a), str(b), str(self.folder)], query="두 파일 비교", store=store)
        wire = result.model_content("read")
        self.assertIn("AAA-111", wire)
        self.assertIn("BBB-222", wire)
        self.assertNotIn(str(self.root), wire)
        self.assertIn("IRIS_FOLDER_TEST", prepare_attachments([], query="src/config.py PROJECT_NAME", store=store).model_content("read"))
        b.unlink()
        self.assertTrue(store.prepare().notices)

    def test_pdf_late_page_retrieval(self):
        from iris.runtime.attachment_context import _read
        import pymupdf
        document = pymupdf.open()
        for _ in range(100):
            document.new_page().insert_text((72, 72), "IRIS PDF TEST\nCODE: PDF-5678")
        document.new_page().insert_text((72, 72), "IRIS PDF TEST\nCODE: TAIL7777")
        path = self.root / "late.pdf"
        document.save(path)
        document.close()
        item = _read(path, budget=2000, query="TAIL7777")
        self.assertIn("TAIL7777", item.text)

    def test_replaced_directory_link_cannot_escape(self):
        store = AttachmentStore()
        store.attach([str(self.folder)])
        aid = next(iter(store.roots))
        with patch("iris.runtime.attachment_store._is_link", side_effect=lambda path: path == self.folder / "src"):
            with self.assertRaises(ValueError):
                store.read_attached_file(aid, "src/config.py")

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_actual_windows_junction_swap_is_blocked(self):
        store = AttachmentStore()
        store.attach([str(self.folder)])
        aid = next(iter(store.roots))
        (self.folder / "src").rename(self.folder / "src-original")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "config.py").write_text("OUTSIDE_SECRET", encoding="utf-8")
        created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(self.folder / "src"), str(outside)],
                                 capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(created.returncode, 0)
        with self.assertRaises(ValueError):
            store.read_attached_file(aid, "src/config.py")
        self.assertNotIn("OUTSIDE_SECRET", store.prepare("src/config.py").model_content("read"))

    def test_many_small_document_parts_are_packed(self):
        from iris.runtime.attachment_context import _read
        with patch("iris.runtime.attachment_context._parts", return_value=iter([f"Paragraph {i}" for i in range(100)])):
            item = _read(self.files["docx"], budget=6000)
        self.assertIn("Paragraph 99", item.text)
        self.assertFalse(item.truncated)

    def test_korean_particle_and_tiny_budget_keep_matching_tail(self):
        from iris.runtime.attachment_context import _read
        path = self.root / "large.py"
        path.write_text("irrelevant\n" * 8000 + 'workspaceRoot = "FOUND-8888"', encoding="utf-8")
        item = _read(path, budget=500, query="workspaceRoot가 쓰인 부분")
        self.assertIn("FOUND-8888", item.text)

    def test_chat_isolation(self):
        from iris.storage.database import Database
        from iris.runtime.chat_session import ChatSession
        db = Database(self.root / "chat.db")
        try:
            session = ChatSession(db)
            old = session.attachments
            old.attach([str(self.folder)])
            session.activate(session.start_new())
            self.assertFalse(session.attachments.roots)
            self.assertIsNot(session.attachments, old)
            self.assertFalse(ChatSession(db).attachments.roots)
        finally:
            db._conn.close()

    def test_copy_and_move_preserve_original_bytes(self):
        source = self.root / "original.pdf"
        source.write_bytes(b"%PDF-1.7\x00original-bytes")
        destination = self.root / "exports"
        destination.mkdir()
        store = AttachmentStore()
        store.attach([str(source)])
        aid = next(iter(store.roots))

        copied = store.copy_to(aid, str(destination))
        self.assertEqual(copied.read_bytes(), source.read_bytes())
        self.assertTrue(source.exists())
        with self.assertRaises(FileExistsError):
            store.copy_to(aid, str(destination))

        moved = store.move_to(aid, str(self.root / "moved.pdf"))
        self.assertFalse(source.exists())
        self.assertEqual(moved.read_bytes(), b"%PDF-1.7\x00original-bytes")
        self.assertEqual(store._resolve(aid, "moved.pdf"), moved)

    def test_transfer_rejects_relative_destination_and_folder_attachment(self):
        source = self.root / "source.txt"
        source.write_text("original", encoding="utf-8")
        store = AttachmentStore()
        store.attach([str(source), str(self.folder)])
        file_id, folder_id = tuple(store.roots)
        with self.assertRaises(ValueError):
            store.copy_to(file_id, "relative.txt")
        with self.assertRaises(ValueError):
            store.copy_to(folder_id, str(self.root / "folder-copy"))

    def test_attachment_limit_keeps_successes_and_bounded_error_state(self):
        store = AttachmentStore()
        paths = []
        for index in range(52):
            path = self.root / f"input-{index}.txt"
            path.write_text(f"CODE: {index}", encoding="utf-8")
            paths.append(str(path))
        store.attach(paths)
        store.attach([paths[-1]])
        self.assertLessEqual(len(store.roots), 51)
        result = store.prepare("CODE")
        self.assertTrue(any("개수 한도" in notice for notice in result.notices))
        self.assertTrue(any(a.text for a in result.attachments))

    def test_actual_project_mcp_search(self):
        project = Path(__file__).resolve().parents[1]
        store = AttachmentStore()
        store.attach([str(project)])
        hits = store.search_attached_files("MCP", limit=50)
        self.assertTrue(hits)
        self.assertTrue(any(h["snippets"] for h in hits))
        self.assertTrue(any("iris/" in h["relative_path"] or "integrations/" in h["relative_path"] for h in hits))
        selected = store.prepare("MCP 관련 코드 구현 파일")
        self.assertTrue(any(a.relative_path == "iris/mcp/iris_control_stdio.py" for a in selected.attachments))
        self.assertTrue(any(a.extracted_text for a in selected.attachments))
        self.assertTrue(all(a.extension in {"py", "js", "ts", "tsx"} for a in selected.attachments if a.extracted_text))
        self.assertLessEqual(sum(len(a.text) for a in selected.attachments), MAX_CONTEXT_CHARS)


if __name__ == "__main__":
    unittest.main()
