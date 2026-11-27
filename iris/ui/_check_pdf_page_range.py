"""PDF page_from/page_to + incomplete manifest self-check.

  .venv\\Scripts\\python.exe -m iris.ui._check_pdf_page_range
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace


def _multi_page_pdf(path: Path, markers: list[str]) -> None:
    import pymupdf

    doc = pymupdf.open()
    for index, marker in enumerate(markers):
        page = doc.new_page(width=420, height=200)
        # Avoid underscores: some built-in fonts render "_" as space.
        page.insert_text((40, 72), f"PAGE{index + 1} {marker}")
    doc.save(str(path))
    doc.close()


def _check_page_range_only() -> None:
    from iris.knowledge.content_extract import extract_from_source

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "range.pdf"
        _multi_page_pdf(pdf, ["ALPHA", "BRAVO", "CHARLIE"])
        data = extract_from_source(str(pdf), page_from=2, page_to=2)
        text = str(data.get("text") or "")
        assert "[쪽 2]" in text, text
        assert "BRAVO" in text, text
        assert "ALPHA" not in text, text
        assert "CHARLIE" not in text, text
        assert int(data.get("total_pages") or 0) == 3, data
        status = list(data.get("page_status") or [])
        assert len(status) == 3, status
        by_page = {int(row["page"]): row for row in status}
        assert by_page[2]["kind"] in {"text", "ocr", "hybrid", "vision"}, by_page[2]
        assert by_page[1]["kind"] == "unread", by_page[1]
        assert by_page[3]["kind"] == "unread", by_page[3]
        assert data.get("incomplete") is True, data


def _check_incomplete_when_unread_remain() -> None:
    from iris.knowledge.content_extract import read_pdf_pages

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "limit.pdf"
        _multi_page_pdf(pdf, ["A", "B", "C", "D"])
        data = read_pdf_pages(pdf, page_limit=2)
        assert int(data.get("total_pages") or 0) == 4, data
        status = list(data.get("page_status") or [])
        assert len(status) == 4, status
        unread = [row for row in status if row.get("kind") == "unread"]
        assert len(unread) == 2, status
        assert data.get("incomplete") is True, data


def _check_chip_exposes_manifest() -> None:
    from iris.runtime.attachment_context import prepare_attachments

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "chip.pdf"
        _multi_page_pdf(pdf, ["ONE", "TWO", "THREE"])
        prepared = prepare_attachments([str(pdf)], query="TWO")
        assert not prepared.notices, prepared.notices
        item = prepared.attachments[0]
        assert item.attachment_id, item
        assert item.total_pages == 3, item
        assert item.page_status, item.page_status
        body = prepared.model_content("요약해줘")
        assert "attachment_id" in body, body
        assert "total_pages" in body, body
        assert "content_extract" in body, body
        assert str(pdf) not in body, body


def _check_resolve_attachment_id() -> None:
    from iris.runtime.attachment_store import AttachmentStore
    from iris.ui.control_actions.wiki import resolve_attachment_source

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "aid.pdf"
        _multi_page_pdf(pdf, ["X", "Y"])
        store = AttachmentStore()
        store.attach([str(pdf)])
        aid = next(iter(store.roots))
        resolved = resolve_attachment_source(store, aid)
        assert Path(resolved).resolve() == pdf.resolve(), resolved
        try:
            resolve_attachment_source(store, "missing-id")
            raise AssertionError("expected missing attachment_id to fail")
        except ValueError as exc:
            assert "not found" in str(exc), exc
        try:
            resolve_attachment_source(None, aid)
            raise AssertionError("expected None store to fail")
        except ValueError as exc:
            assert "not found" in str(exc), exc
        # Window wiring shape used by content.extract
        window = SimpleNamespace(_chat_session=SimpleNamespace(attachments=store))
        store2 = getattr(getattr(window, "_chat_session", None), "attachments", None)
        assert resolve_attachment_source(store2, aid) == resolved


def main() -> None:
    _check_page_range_only()
    _check_incomplete_when_unread_remain()
    _check_chip_exposes_manifest()
    _check_resolve_attachment_id()
    print("pdf_page_range self-check ok")


if __name__ == "__main__":
    main()
