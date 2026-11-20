"""칩 PDF OCR·하이브리드·content.extract 보강 self-check.

TDD 순서 (A → B → C). 구현 전엔 해당 assert에서 실패해야 한다.

  .venv\\Scripts\\python.exe -m iris.ui._check_chip_pdf_enrich
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path


def _hybrid_pdf(path: Path, *, title: str, marker: str) -> None:
    """텍스트 레이어(제목) + 이미지(코드 마커). 강의 슬라이드와 같은 형태."""
    from PIL import Image, ImageDraw

    import pymupdf

    img = Image.new("RGB", (640, 200), "white")
    ImageDraw.Draw(img).text((24, 80), marker, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=640, height=280)
    page.insert_text((72, 48), title)
    page.insert_image(pymupdf.Rect(40, 70, 600, 250), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _scanned_pdf(path: Path, marker: str) -> None:
    from PIL import Image, ImageDraw

    import pymupdf

    img = Image.new("RGB", (480, 120), "white")
    ImageDraw.Draw(img).text((20, 40), marker, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=480, height=120)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _check_a_chip_scan_uses_enrichment() -> None:
    """A: 칩 prepare_attachments가 스캔 PDF에서 OCR/비전 본문을 얻는다."""
    import iris.knowledge.content_extract as content_extract
    from iris.runtime.attachment_context import prepare_attachments

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        _scanned_pdf(pdf, "CHIP_SCAN_MARKER")
        original = content_extract._ocr_png_bytes
        content_extract._ocr_png_bytes = lambda png: ("CHIP_SCAN_MARKER from ocr", "")
        try:
            prepared = prepare_attachments([str(pdf)], query="숫자 인식")
        finally:
            content_extract._ocr_png_bytes = original
        assert not prepared.notices, prepared.notices
        body = "\n".join(a.text for a in prepared.attachments)
        assert "CHIP_SCAN_MARKER" in body, body


def _check_b_hybrid_does_not_skip_ocr() -> None:
    """B: 제목 글자층이 _LAYER_MIN 이상이어도 이미지 쪽이면 OCR을 탄다."""
    import iris.knowledge.content_extract as content_extract
    from iris.knowledge.content_extract import read_pdf_pages

    title = "실습 숫자인식하는 GUI 프로그램 딥러닝 모델 dmlp trained lecture notes"  # >40 letters
    assert content_extract._letters(title) >= content_extract._LAYER_MIN

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "hybrid.pdf"
        _hybrid_pdf(pdf, title=title, marker="HYBRID_CODE_LINE")
        called = {"n": 0}
        original = content_extract._ocr_png_bytes

        def _ocr(png: bytes) -> tuple[str, str]:
            called["n"] += 1
            return ("HYBRID_CODE_LINE from ocr", "")

        content_extract._ocr_png_bytes = _ocr
        try:
            data = read_pdf_pages(pdf, vision_reader=lambda pngs: "")
        finally:
            content_extract._ocr_png_bytes = original
        assert called["n"] >= 1, data
        assert "HYBRID_CODE_LINE" in str(data["text"]), data
        assert data.get("ocr_used") is True, data


def _check_a_chip_hybrid() -> None:
    """A+B: 칩 경로로 하이브리드 PDF를 넣으면 이미지 마커가 본문에 있다."""
    import iris.knowledge.content_extract as content_extract
    from iris.runtime.attachment_context import prepare_attachments

    title = "실습 숫자인식하는 GUI 프로그램 딥러닝 모델 dmlp trained lecture notes"
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "hybrid.pdf"
        _hybrid_pdf(pdf, title=title, marker="CHIP_HYBRID_MARK")
        original = content_extract._ocr_png_bytes
        content_extract._ocr_png_bytes = lambda png: ("CHIP_HYBRID_MARK from ocr", "")
        try:
            prepared = prepare_attachments([str(pdf)], query="7-7")
        finally:
            content_extract._ocr_png_bytes = original
        assert not prepared.notices, prepared.notices
        body = "\n".join(a.text for a in prepared.attachments)
        assert "CHIP_HYBRID_MARK" in body, body


def _check_c_content_extract_flags() -> None:
    """C: content.extract(extract_from_source)가 ocr/vision 사용 여부를 반환한다."""
    import iris.knowledge.content_extract as content_extract
    from iris.knowledge.content_extract import extract_from_source

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        _scanned_pdf(pdf, "EXTRACT_FLAG_MARK")
        original = content_extract._ocr_png_bytes
        content_extract._ocr_png_bytes = lambda png: ("EXTRACT_FLAG_MARK", "")
        try:
            data = extract_from_source(str(pdf))
        finally:
            content_extract._ocr_png_bytes = original
        assert "EXTRACT_FLAG_MARK" in str(data.get("text")), data
        assert data.get("ocr_used") is True, data


def _check_d_query_terms_lab_id() -> None:
    from iris.runtime.attachment_context import collapse_ocr_gaps, query_terms

    terms = query_terms("마지막 실습인 7-7과 동일하도록 수정해줘")
    assert "7-7" in terms, terms
    assert collapse_ocr_gaps("실 습 코 드") == "실습코드"


def _multi_page_tail_pdf(path: Path, *, early: str, late: str) -> None:
    """앞쪽은 긴 글자층, 마지막 쪽에만 실습 마커(이미지)."""
    from PIL import Image, ImageDraw

    import pymupdf

    doc = pymupdf.open()
    for index in range(6):
        page = doc.new_page(width=640, height=280)
        filler = (early + " ") * 40
        page.insert_text((40, 48), f"page {index + 1} {filler}"[:500])
    img = Image.new("RGB", (640, 200), "white")
    ImageDraw.Draw(img).text((24, 80), late, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    last = doc.new_page(width=640, height=280)
    last.insert_text((72, 48), "실습 7-7 숫자인식")
    last.insert_image(pymupdf.Rect(40, 70, 600, 250), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _check_e_tail_query_keeps_last_lab() -> None:
    """E: 「마지막」「7-7」 질문이면 예산이 잘려도 끝쪽 실습 마커가 남는다."""
    import iris.knowledge.content_extract as content_extract
    from iris.runtime.attachment_context import prepare_attachments

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "lecture.pdf"
        _multi_page_tail_pdf(pdf, early="표지판 인식 도로 표지 roadButton", late="TAIL_LAB_7_7_CODE")
        original = content_extract._ocr_png_bytes
        content_extract._ocr_png_bytes = lambda png: ("TAIL_LAB_7_7_CODE from ocr", "")
        try:
            prepared = prepare_attachments(
                [str(pdf)],
                query="이 스크립트를 pdf속 마지막 실습인 7-7과 동일하도록 수정해줘",
            )
        finally:
            content_extract._ocr_png_bytes = original
        assert not prepared.notices, prepared.notices
        body = "\n".join(a.text for a in prepared.attachments)
        assert "TAIL_LAB_7_7_CODE" in body, body


def main() -> None:
    _check_a_chip_scan_uses_enrichment()
    _check_b_hybrid_does_not_skip_ocr()
    _check_a_chip_hybrid()
    _check_c_content_extract_flags()
    _check_d_query_terms_lab_id()
    _check_e_tail_query_keeps_last_lab()
    print("chip_pdf_enrich self-check ok")


if __name__ == "__main__":
    main()
