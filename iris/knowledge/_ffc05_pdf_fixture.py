"""FFC-05: generate a 201-page PDF with unique per-page markers (not checked into git)."""

from __future__ import annotations

from pathlib import Path

FFC05_PAGE_COUNT = 201


def ffc05_page_value(page: int) -> int:
    """Deterministic value for page N (1-based)."""
    return int(page) * 9973 + 17


def ffc05_page_marker(page: int) -> str:
    """Unique marker for page N. No underscores (built-in PDF fonts may drop them)."""
    n = int(page)
    return f"IRIS-FFC05-P{n:03d}-VAL={ffc05_page_value(n)}"


def ffc05_page_prose(page: int) -> str:
    n = int(page)
    return f"Unique prose for fixture page {n} of {FFC05_PAGE_COUNT}."


def write_ffc05_201p_pdf(path: Path, *, page_count: int = FFC05_PAGE_COUNT) -> Path:
    """Write a multi-page PDF; each page holds its marker + short unique prose."""
    import pymupdf

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    try:
        for page_num in range(1, int(page_count) + 1):
            page = doc.new_page(width=420, height=200)
            page.insert_text((40, 72), ffc05_page_marker(page_num))
            page.insert_text((40, 100), ffc05_page_prose(page_num))
        doc.save(str(out))
    finally:
        doc.close()
    return out
