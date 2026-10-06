"""Actual files through Qt selection/drop, extraction, persistence and HTTP payloads."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("IRIS_ATTACHMENT_LOG_DIR", str(Path(__file__).resolve().parents[1] / ".iris_light_test_tmp" / "attachments"))

from iris.runtime.attachment_context import MAX_CONTEXT_CHARS, MAX_FILE_BYTES, inference_messages, prepare_attachments
from iris.runtime.chat_session import ChatSession
from iris.storage.database import Database


def create_fixtures(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {ext: root / f"test.{ext}" for ext in ("txt", "pdf", "pptx", "docx", "xlsx")}
    paths["txt"].write_text("IRIS FILE TEST\nCODE: TXT-1234", encoding="utf-8")
    import pymupdf
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "IRIS PDF TEST\nCODE: PDF-5678")
    document.save(paths["pdf"])
    document.close()
    with zipfile.ZipFile(paths["pptx"], "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
        z.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>')
        z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Test"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>SLIDE TEST</a:t></a:r></a:p><a:p><a:r><a:t>CODE: PPT-9999</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
    with zipfile.ZipFile(paths["docx"], "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>CODE: DOC-2222</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(paths["xlsx"], "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>CODE: XLS-3333</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>1+1</f><v>2</v></c><c r="C1" t="inlineStr"><is><t>inline</t></is></c></row></sheetData></worksheet>')
    return paths


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.files = create_fixtures(self.root)

    def tearDown(self):
        self.tmp.cleanup()


class AttachmentTests(FixtureCase):

    def test_required_file_formats_and_metadata(self):
        for extension, code in [("txt", "TXT-1234"), ("pdf", "PDF-5678"), ("pptx", "PPT-9999"), ("docx", "DOC-2222"), ("xlsx", "XLS-3333")]:
            with self.subTest(extension=extension):
                result = prepare_attachments([str(self.files[extension])])
                item = result.attachments[0]
                self.assertEqual(item.error, "")
                self.assertIn(code, item.text)
                self.assertGreater(item.size, 0)
                self.assertEqual(item.filename, f"test.{extension}")
                self.assertTrue(item.mime_type)
                self.assertTrue(item.id)
                self.assertNotIn(str(self.root), result.model_content("이거 읽어줘"))
                self.assertNotIn('"path"', result.model_content("이거 읽어줘"))

    def test_text_formats_encodings(self):
        for extension in ["md", "json", "csv", "py", "ts", "yaml"]:
            path = self.root / f"source.{extension}"
            path.write_text("CODE: TEXT-4444", encoding="utf-8")
            self.assertIn("TEXT-4444", prepare_attachments([str(path)]).attachments[0].text)
        for encoding in ["utf-16", "cp949"]:
            path = self.root / "한글 파일.txt"
            path.write_bytes("한글 CODE: KR-5555".encode(encoding))
            self.assertIn("한글", prepare_attachments([str(path)]).attachments[0].text)

    def test_per_file_errors_and_deleted_file(self):
        paths = [self.root / "deleted.txt", self.root / "empty.txt", self.root / "unsupported.bin", self.root / "large.txt", self.root / "corrupt.pptx"]
        paths[1].touch()
        paths[2].write_bytes(b"binary")
        with paths[3].open("wb") as handle:
            handle.truncate(MAX_FILE_BYTES + 1)
        paths[4].write_bytes(b"broken")
        result = prepare_attachments([*(str(p) for p in paths), str(self.files["txt"])])
        self.assertTrue(all(a.error for a in result.attachments[:5]))
        self.assertIn("지원하지", result.attachments[2].error)
        self.assertIn("TXT-1234", result.attachments[-1].text)
        with patch("iris.runtime.attachment_context._parts", side_effect=PermissionError("secret path")):
            result = prepare_attachments([str(self.files["txt"])])
        self.assertIn("잠겨", result.attachments[0].error)
        self.assertNotIn("secret path", result.attachments[0].error)

    def test_size_budget_is_explicit(self):
        path = self.root / "long.txt"
        path.write_text("x" * (MAX_CONTEXT_CHARS + 100), encoding="utf-8")
        result = prepare_attachments([str(path), str(self.files["txt"])])
        self.assertTrue(result.attachments[0].truncated)
        self.assertLessEqual(sum(len(a.text) for a in result.attachments), MAX_CONTEXT_CHARS)

    def test_large_text_selects_query_related_tail(self):
        path = self.root / "long.txt"
        path.write_text("irrelevant\n" * 5000 + "CODE: TAIL-9090", encoding="utf-8")
        result = prepare_attachments([str(path)], query="CODE 값을 알려줘")
        self.assertTrue(result.attachments[0].truncated)
        self.assertIn("TAIL-9090", result.attachments[0].text)
        self.assertLessEqual(len(result.attachments[0].text), MAX_CONTEXT_CHARS)

    def test_scanned_and_encrypted_pdf_have_specific_errors(self):
        from pypdf import PdfWriter
        path = self.root / "scan.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=200)
        with path.open("wb") as handle:
            writer.write(handle)
        result = prepare_attachments([str(path)])
        self.assertIn("스캔 PDF", result.attachments[0].error)
        self.assertEqual(result.attachments[0].text, "")
        writer.encrypt("password")
        with path.open("wb") as handle:
            writer.write(handle)
        self.assertIn("암호화", prepare_attachments([str(path)]).attachments[0].error)

    @unittest.skipUnless(os.name == "nt", "Windows sharing locks")
    def test_actual_windows_exclusive_file_lock_is_per_file_error(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.files["txt"]), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            result = prepare_attachments([str(self.files["txt"]), str(self.files["pdf"])])
            self.assertTrue(result.attachments[0].error)
            self.assertIn("PDF-5678", result.attachments[1].text)
        finally:
            kernel.CloseHandle(handle)

    def test_folder_exclusions_and_contents(self):
        folder = self.root / "project"
        folder.mkdir()
        (folder / "app.py").write_text("CODE: FOLDER-7777", encoding="utf-8")
        for excluded in ["node_modules", ".git", "dist", "build", "venv", ".venv"]:
            (folder / excluded).mkdir()
            (folder / excluded / "secret.txt").write_text("EXCLUDED_SECRET", encoding="utf-8")
        result = prepare_attachments([str(folder)])
        self.assertIn("FOLDER-7777", result.model_content("read folder"))
        self.assertNotIn("EXCLUDED_SECRET", result.model_content("read folder"))
        self.assertIn("app.py", result.attachments[-1].text)

    def test_persistence_and_followup_separate_display_from_model(self):
        database = Database(self.root / "chat.db")
        session = ChatSession(database)
        prepared = prepare_attachments([str(self.files["txt"])])
        session.record("user", '이거 읽어줘\n@"test.txt"', model_content=prepared.model_content("이거 읽어줘"))
        self.files["txt"].unlink()
        restored = ChatSession(database)
        self.assertNotIn("TXT-1234", restored.history[0]["content"])
        self.assertIn("TXT-1234", inference_messages(restored.history)[0]["content"])
        restored.record("user", "CODE 다시 알려줘")
        self.assertIn("TXT-1234", inference_messages(restored.history)[0]["content"])
        self.assertNotIn("model_content", inference_messages(restored.history)[0])
        database._conn.close()

    def test_image_ocr_and_clear_failure(self):
        path = self.root / "image.png"
        path.write_bytes(b"image fixture")
        with patch("iris.runtime.attachment_context._ocr_image", return_value="CODE: IMAGE-8888"):
            self.assertIn("IMAGE-8888", prepare_attachments([str(path)]).attachments[0].text)
        with patch("iris.runtime.attachment_context._ocr_image", side_effect=RuntimeError("missing OCR")):
            self.assertTrue(prepare_attachments([str(path)]).attachments[0].error)

    def test_image_vision_then_path(self):
        from iris.runtime.attachment_context import bind_chat_image_reader, reset_chat_image_reader

        path = self.root / "shot.png"
        path.write_bytes(b"not-a-real-png")
        seen: list[bytes] = []

        def reader(png: bytes) -> str:
            seen.append(png)
            return "import cv2 as cv\nsoccer.jpg"

        token = bind_chat_image_reader(reader)
        try:
            with patch("iris.knowledge.content_extract._png_bytes", return_value=b"PNGBYTES"), patch(
                "iris.knowledge.content_extract._ocr_png_bytes",
                return_value=("", "ocr should not run"),
            ):
                prepared = prepare_attachments([str(path)])
        finally:
            reset_chat_image_reader(token)
        item = prepared.attachments[0]
        self.assertIn("import cv2", item.text)
        self.assertEqual(seen, [b"PNGBYTES"])
        body = prepared.model_content("추출해줘")
        self.assertIn("Attachment path: " + str(path), body)
        self.assertNotIn('@"', body)


class QtAttachmentTests(FixtureCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFontDatabase
        cls.app = QApplication.instance() or QApplication([])
        for font in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/segoeui.ttf"):
            if Path(font).is_file():
                QFontDatabase.addApplicationFont(font)
        cls.surfaces = []  # Keep Qt drop-hint singleShot targets alive throughout the suite.

    def send_file(self, panel, path, *, drop):
        from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PyQt6.QtGui import QDropEvent
        panel._input_area.attachment_strip.clear_paths()
        if drop:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            panel.dropEvent(QDropEvent(QPointF(8, 8), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        else:
            # Same callback the native file picker uses after selection.
            panel._input_area.input_bar._on_paths_attached([str(path)])
        panel.set_input_text("이 파일 안에 있는 CODE 값을 알려줘.")
        sent = []
        callback = lambda question, paths: sent.append((question, paths))
        panel.send_clicked.connect(callback)
        panel._emit_send()
        panel.send_clicked.disconnect(callback)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], [str(path)])
        self.assertNotIn(str(path), sent[0][0])
        return sent[0]

    def test_picker_drop_and_ide_mount_use_same_pipeline(self):
        from PyQt6.QtWidgets import QWidget, QVBoxLayout
        from iris.ui.chat.chat_panel import ChatPanel
        from iris.ui.workspaces.ide_companion_page import IdeCompanionPage
        from iris.ui.chat.chat_renderer import render_user_message
        panel = ChatPanel()
        panel.set_workspace_root(str(self.root))
        companion = IdeCompanionPage()
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.addWidget(panel)
        self.surfaces.extend([panel, companion, main])
        for mode in ["main", "ide"]:
            if mode == "ide":
                companion.mount(orb_spacer=QWidget(), live_activity=QWidget(), chat=panel, activity_height=40)
            for extension, code in [("txt", "TXT-1234"), ("pdf", "PDF-5678"), ("pptx", "PPT-9999")]:
                for drop in [False, True]:
                    with self.subTest(mode=mode, extension=extension, drop=drop):
                        question, paths = self.send_file(panel, self.files[extension], drop=drop)
                        prepared = prepare_attachments(paths)
                        self.assertIn(code, prepared.model_content(question))
                        rendered = render_user_message(question + '\n@"' + self.files[extension].name + '"')
                        self.assertIn(self.files[extension].name, rendered)
                        self.assertNotIn(str(self.root), rendered)
            if mode == "ide":
                companion.transfer_to(main_layout, (0, 0, 1))

    def test_background_worker_delivers_bytes_as_text(self):
        from iris.ui.workers.attachment_worker import AttachmentWorker
        worker = AttachmentWorker([str(self.files["pptx"])])
        received = []
        worker.prepared.connect(received.append)
        worker.start()
        deadline = time.monotonic() + 10
        while not received and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        worker.wait(1000)
        self.assertTrue(received)
        self.assertIn("PPT-9999", received[0].model_content("read"))

    def test_native_folder_picker_uses_shared_callback(self):
        from iris.ui.chat.chat_panel import ChatPanel
        panel = ChatPanel()
        self.surfaces.append(panel)
        received = []
        panel._input_area.input_bar.files_attached.connect(received.append)
        with patch("iris.ui.chat.chat_panel.QFileDialog.getExistingDirectory", return_value=str(self.root)):
            panel._input_area.input_bar._pick_folder()
        self.assertEqual(received, [[str(self.root)]])

    def test_production_main_window_dispatch_and_deleted_after_selection(self):
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        from iris.ui.chat.chat_panel import ChatPanel
        from iris.ui.workspaces.ide_companion_page import IdeCompanionPage
        from scripts.check_attachment_live import DispatchHarness
        panel = ChatPanel()
        database = Database(self.root / "dispatch.db")
        harness = DispatchHarness(panel, database)
        panel.send_clicked.connect(harness._on_user_text)
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.addWidget(panel)
        main.resize(700, 600)
        main.setStyleSheet("background-color: #080d19; color: #e2e8f0;")
        companion = IdeCompanionPage()
        companion.resize(400, 700)
        self.surfaces.extend([panel, companion, main, harness])
        screenshots = Path(__file__).resolve().parents[1] / ".iris_light_test_tmp" / "attachments"
        screenshots.mkdir(parents=True, exist_ok=True)
        for mode in ["main", "ide"]:
            if mode == "ide":
                companion.mount(orb_spacer=QWidget(), live_activity=QWidget(), chat=panel, activity_height=40)
            for drop in [False, True]:
                panel.clear_transcript()
                before = len(harness.payloads)
                self.send_file(panel, self.files["pptx"], drop=drop)
                deadline = time.monotonic() + 10
                while len(harness.payloads) == before and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.01)
                self.assertGreater(len(harness.payloads), before)
                self.assertIn("PPT-9999", harness.payloads[-1][-1]["content"])
                self.assertNotIn(str(self.root), harness._history[-1]["content"])
                self.assertNotIn("PPT-9999", panel._log.toPlainText())
                self.assertIn("test.pptx", panel._log.toPlainText())
                harness._chat_worker.wait(1000)
            surface = main if mode == "main" else companion
            surface.show()
            self.app.processEvents()
            surface.grab().save(str(screenshots / f"{mode}-attachment.png"))
            if mode == "ide":
                companion.transfer_to(layout, (0, 0, 1))
        # The file existed when picked and was deleted before send.
        harness._chat_session.clear_messages()
        panel._input_area.input_bar._on_paths_attached([str(self.files["txt"])])
        self.files["txt"].unlink()
        panel.set_input_text("이거 읽어줘")
        before = len(harness.payloads)
        panel._emit_send()
        deadline = time.monotonic() + 10
        while harness._turn_gate.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        harness._chat_worker.wait(1000)
        self.assertEqual(len(harness.payloads), before)
        self.assertIn("삭제", panel._log.toPlainText())
        self.assertFalse(harness.failures)
        database._conn.close()
        main.close()
        companion.close()


class WirePayloadTests(FixtureCase):
    def test_actual_hermes_http_request_contains_body_and_no_local_path(self):
        from iris.infrastructure.hermes_client import HermesClient
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"hermes-agent"}]}')
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"TXT-1234"}}]}\n\ndata: [DONE]\n\n')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            prepared = prepare_attachments([str(self.files["txt"])])
            messages = inference_messages([{"role": "user", "content": "read", "model_content": prepared.model_content("read")}])
            response = "".join(e.get("content") or "" for e in HermesClient(f"http://127.0.0.1:{server.server_port}").stream_chat("test", messages))
            self.assertEqual(response, "TXT-1234")
            self.assertIn("TXT-1234", captured[0]["messages"][0]["content"])
            self.assertNotIn(str(self.root), json.dumps(captured[0]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
