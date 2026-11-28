"""FFC-05 Document L2: 201-page PDF page-range extract (no live model / L4).

  .venv\\Scripts\\python.exe -m iris.ui._check_ffc05_pdf_201p

L4 (live model reading the fixture) is out of scope here — UNVERIFIED.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _assert_window(path: Path, page: int) -> str:
    from iris.knowledge._ffc05_pdf_fixture import ffc05_page_marker
    from iris.knowledge.content_extract import extract_from_source

    data = extract_from_source(str(path), page_from=page, page_to=page)
    text = str(data.get("text") or "")
    marker = ffc05_page_marker(page)
    assert int(data.get("total_pages") or 0) == 201, data
    assert marker in text, (page, marker, text[:500])
    assert f"[쪽 {page}]" in text, text[:500]
    # Unread pages must not invent their values into this window.
    if page != 1:
        assert ffc05_page_marker(1) not in text, text[:500]
    status = list(data.get("page_status") or [])
    assert len(status) == 201, len(status)
    by_page = {int(row["page"]): row for row in status}
    assert by_page[page]["kind"] in {"text", "ocr", "hybrid", "vision"}, by_page[page]
    if page != 1:
        assert by_page[1]["kind"] == "unread", by_page[1]
    return text


def main() -> None:
    from iris.knowledge._ffc05_pdf_fixture import (
        FFC05_PAGE_COUNT,
        ffc05_page_marker,
        write_ffc05_201p_pdf,
    )
    from iris.knowledge.content_extract import extract_from_source, read_pdf_pages

    assert FFC05_PAGE_COUNT == 201

    with tempfile.TemporaryDirectory() as tmp:
        pdf = write_ffc05_201p_pdf(Path(tmp) / "ffc05-201p.pdf")

        # page 87 only
        text87 = _assert_window(pdf, 87)
        assert ffc05_page_marker(201) not in text87, text87[:500]
        assert ffc05_page_marker(86) not in text87, text87[:500]
        assert ffc05_page_marker(88) not in text87, text87[:500]

        # page 201 only (page_from alone)
        data201 = extract_from_source(str(pdf), page_from=201)
        text201 = str(data201.get("text") or "")
        assert ffc05_page_marker(201) in text201, text201[:500]
        assert ffc05_page_marker(1) not in text201, text201[:500]
        assert ffc05_page_marker(87) not in text201, text201[:500]
        assert int(data201.get("total_pages") or 0) == 201

        # read_pdf_pages path (same window contract)
        via_read = read_pdf_pages(pdf, page_from=87, page_to=87)
        assert ffc05_page_marker(87) in str(via_read.get("text") or "")
        assert int(via_read.get("total_pages") or 0) == 201
        assert ffc05_page_marker(1) not in str(via_read.get("text") or "")

    print("ffc05_pdf_201p L2 self-check ok (L4 live model UNVERIFIED)")


if __name__ == "__main__":
    main()
