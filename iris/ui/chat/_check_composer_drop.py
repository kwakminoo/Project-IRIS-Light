"""Composer 드롭 @경로 변환 · 칩 self-check."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel

from iris.ui.chat.chat_panel import ChatPanel, _quote_at_ref
from iris.ui.chat.chat_renderer import render_user_message
from iris.ui.chat.composer_attachments import (
    composer_chip_label,
    composer_chip_meta,
    format_byte_size,
    format_user_attachment_block,
    partition_attachment_paths,
)
from iris.knowledge.content_extract import extract_from_source
from iris.ui.chat.at_path_refs import resolve_at_kind


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    root = Path(__file__).resolve().parents[3]
    panel.set_workspace_root(str(root))
    ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat" / "chat_panel.py"))
    assert ref == "@iris/ui/chat/chat_panel.py", ref
    assert panel._path_to_at_ref("@integrations/iris-ide/tsconfig.json") == "@integrations/iris-ide/tsconfig.json"
    folder_ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat"))
    assert folder_ref == "@iris/ui/chat", folder_ref
    panel._on_composer_drop_paths(
        [ref, str(root / "iris" / "assets" / "iris_icon.png"), str(root / "iris" / "ui" / "chat")]
    )
    chips = panel._input_area.attachment_strip.paths()
    assert ref in chips, chips
    assert str(root / "iris" / "ui" / "chat") in chips, chips
    assert composer_chip_label(ref) == "chat_panel.py", composer_chip_label(ref)
    assert composer_chip_label(folder_ref) == "chat", composer_chip_label(folder_ref)
    win = "@C:/Users/serin/network_security.pdf"
    assert composer_chip_label(win) == "network_security.pdf", composer_chip_label(win)
    korean = r"C:\Users\serin\Documents\실전모의고사(엑셀).pdf"
    spaced = r"C:\Users\serin\Documents\보고서 최종본.pdf"
    assert composer_chip_label(korean) == "실전모의고사(엑셀).pdf", composer_chip_label(korean)
    assert composer_chip_label(spaced) == "보고서 최종본.pdf", composer_chip_label(spaced)
    assert composer_chip_label("@" + korean.replace("\\", "/")) == "실전모의고사(엑셀).pdf"
    lined = "@iris/ui/chat/chat_panel.py:10:2"
    assert composer_chip_label(lined) == "chat_panel.py", composer_chip_label(lined)
    assert panel.acceptDrops() is True
    assert panel._log.acceptDrops() is True
    py = root / "iris" / "ui" / "chat" / "chat_panel.py"
    meta = composer_chip_meta(str(py), workspace_root=str(root))
    assert meta.startswith("PY · "), meta
    assert format_byte_size(1536) == "1.5 KB"
    texts = [w.text() for w in panel._input_area.attachment_strip.findChildren(QLabel)]
    assert any(t.startswith("PY · ") for t in texts), texts
    assert any(t == "chat_panel.py" for t in texts), texts

    missing = str(root / "no-such-attachment.xyz")
    ok, errors = partition_attachment_paths([missing, str(py)])
    assert ok == [str(py)], ok
    assert errors and "찾을 수 없습니다" in errors[0], errors
    panel._on_composer_drop_paths([missing])
    assert "찾을 수 없습니다" in panel._input_area.attach_notice.text()
    # 용량·확장자 상한은 파일 선택(All Files)과 같다. 있는 파일은 형식과 무관하게 칩이 된다.
    odd = Path(tempfile.gettempdir()) / "iris_drop_odd.bin"
    odd.write_bytes(b"abc")
    try:
        before = len(panel._input_area.attachment_strip.paths())
        panel._input_area.input_bar._on_paths_attached([str(odd)])
        assert len(panel._input_area.attachment_strip.paths()) == before + 1
        odd_meta = composer_chip_meta(str(odd))
        assert odd_meta.startswith("BIN · "), odd_meta
    finally:
        odd.unlink(missing_ok=True)

    panel._input_area.attachment_strip._remove(
        panel._input_area.attachment_strip.paths()[-1]
    )

    png = root / "iris" / "assets" / "iris_icon.png"
    pdf = Path(tempfile.gettempdir()) / "iris_drop_sample.pdf"
    doc = Path(tempfile.gettempdir()) / "iris_drop_sample.txt"
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 18 Tf 36 100 Td (IRIS_PDF_MARK) Tj ET")
    page[NameObject("/Contents")] = stream
    with pdf.open("wb") as handle:
        writer.write(handle)
    doc.write_text("hello", encoding="utf-8")
    try:
        panel._input_area.attachment_strip.clear_paths()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(png)), QUrl.fromLocalFile(str(pdf)), QUrl.fromLocalFile(str(doc))])
        panel.dropEvent(
            QDropEvent(
                QPointF(8, 8),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        dropped = panel._input_area.attachment_strip.paths()
        assert len(dropped) == 3, dropped
        assert panel._input.text() == ""
        assert any(p.endswith(".png") or p.endswith("iris_icon.png") for p in dropped), dropped
        shown = [w.text() for w in panel._input_area.attachment_strip.findChildren(QLabel)]
        assert any(t.startswith("PDF · ") for t in shown), shown
        assert any(t.startswith("TXT · ") for t in shown), shown
        thumbs = [
            w for w in panel._input_area.attachment_strip.findChildren(QLabel)
            if w.pixmap() is not None and not w.pixmap().isNull()
        ]
        assert thumbs, shown
        assert not any(t.startswith("PNG · ") for t in shown), shown
        preview = render_user_message(format_user_attachment_block("사진", [str(png)]))
        assert "<img " in preview, preview
        assert "iris-image:" in preview, preview
        assert "PNG ·" not in preview, preview
        video = Path(tempfile.gettempdir()) / "iris_drop_sample.mp4"
        try:
            import cv2
            import numpy as np

            writer = cv2.VideoWriter(
                str(video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                5,
                (64, 48),
            )
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            frame[:, :] = (30, 160, 40)
            writer.write(frame)
            writer.release()
            if video.is_file() and video.stat().st_size > 0:
                video_html = render_user_message(format_user_attachment_block("", [str(video)]))
                assert "<img " in video_html, video_html
                assert "iris-video:" in video_html, video_html
                assert "MP4 ·" not in video_html, video_html
        finally:
            video.unlink(missing_ok=True)
        sent: list[tuple[str, list]] = []
        panel.send_clicked.connect(lambda text, images: sent.append((text, list(images))))
        panel.set_input_text("첨부 확인")
        panel._emit_send()
        assert sent and "첨부 확인" in sent[0][0], sent
        assert any(str(p).endswith("iris_icon.png") for p in sent[0][1]), sent
        assert set(sent[0][1]) == {str(png), str(pdf), str(doc)}, sent
        assert sent[0][0] == "첨부 확인", sent
        payload = sent[0][0] + '\n@"iris_drop_sample.pdf"\n@"iris_drop_sample.txt"'
        html_doc = render_user_message(payload)
        assert "iris_drop_sample.pdf" in html_doc
        assert "iris_drop_sample.txt" in html_doc
        assert "C:/" not in html_doc and "C:\\" not in html_doc, html_doc
        fenced = render_user_message("```python\nprint('ok')\n```\n" + payload)
        assert "print" in fenced and "iris_drop_sample.pdf" in fenced
        assert composer_chip_label(r"C:\Users\serin\document.pdf") != "C"
        panel._input_area.attachment_strip.clear_paths()
        panel._input_area.input_bar._on_paths_attached([str(pdf), str(root)])
        picked = panel._input_area.attachment_strip.paths()
        panel._input_area.attachment_strip.clear_paths()
        panel._on_composer_drop_paths([str(pdf), str(root)])
        dropped_same = panel._input_area.attachment_strip.paths()
        assert [Path(p).name for p in picked] == [Path(p).name for p in dropped_same]
        chips_ui = panel._input_area.attachment_strip.findChildren(QLabel)
        assert any(w.text() == "iris_drop_sample.pdf" for w in chips_ui)
        assert any(w.text() == root.name for w in chips_ui)
        assert all(w.text() != "C" for w in chips_ui)
        folder_hit = resolve_at_kind(_quote_at_ref(str(root)).lstrip("@").strip('"'))
        assert folder_hit["kind"] == "folder", folder_hit
        got = extract_from_source(str(doc))
        assert got["kind"] == "text" and "hello" in str(got["text"])
        pdf_hit = extract_from_source(str(pdf))
        assert pdf_hit["kind"] == "pdf", pdf_hit
        assert "IRIS_PDF_MARK" in str(pdf_hit["text"]), pdf_hit
        panel._input_area.attachment_strip.clear_paths()
    finally:
        pdf.unlink(missing_ok=True)
        doc.unlink(missing_ok=True)

    panel.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            QPointF(8, 8),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert panel._drop_hint.isHidden() is True
    panel.note_file_drag(True, force=True)
    assert panel._drop_hint.isHidden() is False
    panel.dragLeaveEvent(QDragLeaveEvent())
    panel._hide_drop_hint(panel._drop_hint_gen)
    assert panel._drop_hint.isHidden() is True

    one = QMimeData()
    one.setUrls([QUrl.fromLocalFile(str(py))])
    enter = QDragEnterEvent(
        QPoint(4, 4),
        Qt.DropAction.CopyAction,
        one,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert panel._input.eventFilter(panel._input.viewport(), enter) is True
    assert enter.isAccepted()
    print("composer_drop ok", ref, "folder", folder_ref, "chips", len(chips))
    app.quit()


if __name__ == "__main__":
    main()
