from __future__ import annotations
import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QTextDocument
from iris.core.activity_privacy import prepare_chat_text
from iris.ui.chat.markdown_normalization import normalize_markdown_source
from iris.ui.chat.chat_renderer import render_iris_message
from iris.ui.chat.chat_panel import ChatPanel
from iris.system.hermes_gateway import _serialized_lifecycle, GatewayDiagnosis

class RenderingPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_malformed_model_markdown_becomes_rich_document(self):
        source = ("설명입니다.---### 제목\n내용입니다.#### **1단계: SYN**\n"
                  "_**누가 보냄:**_\n**클라이언트 → 서버**\n"
                  "| 단계 | 메시지 |\n| --- | --- |\n| 1 | SYN |\n\n"
                  "1.**항목**\n2.**항목**\n\n&#xC640; &amp;#xC785;\n\n"
                  "> 인용문\n\n[링크](https://example.com)\n\n`inline code`")
        rendered = render_iris_message(source)
        doc = QTextDocument()
        doc.setHtml(rendered)
        text = doc.toPlainText()
        for marker in ("###", "**", "_**", "&#", "| 단계", "1.**"):
            self.assertNotIn(marker, text)
        self.assertIn("와 입", text)
        self.assertIn("<table", rendered)
        self.assertIn("<ol", rendered)
        self.assertIn("<blockquote", rendered)
        self.assertIn("<em>", rendered)
        self.assertIn("<h4", rendered)

    def test_code_is_preserved_including_indentation_and_entities(self):
        code = 'if True:\n    print("### **bold** &#xC640; \\rightarrow")'
        source = f"```python\n{code}\n```"
        self.assertEqual(prepare_chat_text(source), source)
        self.assertEqual(normalize_markdown_source(source), source)
        from iris.ui.chat.chat_blocks import parse_copy_anchor
        import re
        rendered = render_iris_message(source)
        href = re.search(r'href="(iris-copy://[^"]+)"', rendered)[1]
        self.assertEqual(parse_copy_anchor(href), code + "\n")
        self.assertEqual(normalize_markdown_source('`&#xC640;`'), '`&#xC640;`')

    def test_all_chunk_boundaries_and_prior_messages_are_preserved(self):
        source = "### 제목\n\n&#xC640; **굵게**\n\n| A | B |\n|---|---|\n|1|2|\n\n```python\nif True:\n    print(1)\n```"
        panel = ChatPanel()
        panel.append_message_instant("You", "이전 사용자 메시지")
        panel.begin_stream_message("Iris", speech_sync=False)
        for char in source:
            panel.append_stream_chunk(char)
        self.assertEqual(panel._typing_text, source)
        panel.end_stream_message(source)
        panel.finish_typing()
        self.assertIn("이전 사용자 메시지", panel._log.toPlainText())
        self.assertNotIn("&#xC640;", panel._log.toPlainText())
        self.assertNotIn("###", panel._log.toPlainText())
        self.assertIn("iris-copy://", panel._log.toHtml())
        panel.append_error_message("Hermes 요청 실패", "command: internal\nstderr: failure")
        self.assertNotIn("command: internal", panel._log.toPlainText())
        self.assertIn("자세히 보기", panel._log.toPlainText())
        self.assertIn("command: internal", panel._log._error_details["1"])
        panel.close()

    def test_qt_parser_fallback_supports_tables(self):
        import builtins
        original = builtins.__import__
        def without_markdown(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("test missing parser")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=without_markdown):
            rendered = render_iris_message("# 제목\n\n| A | B |\n|---|---|\n|1|2|")
        self.assertIn("<table", rendered)

    def test_gateway_lifecycle_serializes_competing_workers(self):
        active = []
        overlaps = []
        @_serialized_lifecycle
        def operation():
            active.append(1)
            overlaps.append(len(active))
            time.sleep(0.02)
            active.pop()
        threads = [threading.Thread(target=operation) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(overlaps, [1, 1, 1, 1])
        self.assertNotIn("command", GatewayDiagnosis(message="종료", command=["internal"]).chat_message())

    def test_hermes_whitespace_deltas_reach_markdown_parser(self):
        from iris.infrastructure.hermes_client import _should_emit_assistant_content
        chunks = ["###", " ", "제목", "\n\n", "| A | B |", "\n", "|---|---|", "\n", "|1|2|"]
        kept = [chunk for chunk in chunks if _should_emit_assistant_content(chunk, {"delta": {"content": chunk}})]
        self.assertEqual(kept, chunks)
        rendered = render_iris_message("".join(kept))
        self.assertIn("<h3", rendered)
        self.assertIn("<table", rendered)

    def test_math_display_does_not_rewrite_money_or_literal_code(self):
        rendered = render_iris_message(r"$n$ $\frac{n(n+1)}{2}$ $\text{Seq}$; cost $10 and $20")
        self.assertNotIn(r"\frac", rendered)
        self.assertNotIn(r"\text", rendered)
        self.assertIn("cost $10 and $20", rendered)
        self.assertIn("math-cache", rendered)

    def test_display_math_matrix_is_an_image_and_code_keeps_source(self):
        sample = (
            "회전.\n\n$$\n"
            r"R(30^{\circ})=\begin{bmatrix}0.866&0.5&0\\-0.5&0.866&0\\0&0&1\end{bmatrix}"
            "\n$$\n"
        )
        rendered = render_iris_message(sample)
        self.assertIn("<img", rendered)
        self.assertNotIn("bmatrix", rendered)
        self.assertNotIn(r"\begin", rendered)
        fenced = render_iris_message("```text\n\\begin{bmatrix}1\\end{bmatrix}\n```")
        self.assertIn("bmatrix", fenced)
        self.assertNotIn("math-cache", fenced)

if __name__ == "__main__":
    unittest.main()
