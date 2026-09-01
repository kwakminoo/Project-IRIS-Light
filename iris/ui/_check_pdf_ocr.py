"""ponytail: 스캔 PDF OCR 폴백 self-check.

  py -3 -m iris.ui._check_pdf_ocr
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from iris.knowledge.content_extract import (
    _extract_pdf_text_pypdf,
    extract_pdf_text,
)


def _make_scanned_pdf(path: Path, label: str) -> None:
    from PIL import Image, ImageDraw

    import pymupdf

    img = Image.new("RGB", (480, 120), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), label, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=480, height=120)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        label = "IRIS_OCR_TEST"
        _make_scanned_pdf(pdf, label)

        assert not _extract_pdf_text_pypdf(pdf).strip(), "scanned fixture should have no text layer"

        try:
            from iris.knowledge.content_extract import _ensure_tesseract

            _ensure_tesseract()
        except Exception as exc:
            print(f"pdf_ocr self-check: skip OCR integration ({exc})")
            return 0

        text = extract_pdf_text(pdf)
        norm = text.upper().replace("_", " ")
        assert "IRIS" in norm and "TEST" in norm, text

    print("pdf_ocr self-check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
