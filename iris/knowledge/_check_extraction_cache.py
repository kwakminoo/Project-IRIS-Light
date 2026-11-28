"""FFC-05 extraction cache self-check (DESIGN §5)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from iris.knowledge.content_extract import extract_from_source
from iris.knowledge.extraction_cache import (
    ExtractionCacheKey,
    default_engine_probe,
    fingerprint_for,
    get,
    invalidate,
    make_key,
    memo_for_store,
)
from iris.runtime.attachment_store import AttachmentStore


def _tiny_pdf(path: Path, text: str = "hello cache") -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def main() -> int:
    store = AttachmentStore()
    memo = memo_for_store(store)
    engine = default_engine_probe()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "doc.pdf"
        _tiny_pdf(pdf, "page one body")

        from iris.knowledge import content_extract as ce

        # 1. Same image twice → _ocr_for_document runs once.
        from PIL import Image

        png = root / "scan.png"
        Image.new("RGB", (8, 8), color=(255, 255, 255)).save(png)
        ocr_calls = {"n": 0}

        def _count_ocr(png_bytes, language, cancelled):
            ocr_calls["n"] += 1
            return "ocr-text-once", ""

        with patch("iris.knowledge.content_extract._ocr_for_document", side_effect=_count_ocr):
            a = extract_from_source(str(png), memo=memo, attachment_id="att-img")
            b = extract_from_source(str(png), memo=memo, attachment_id="att-img")
        assert ocr_calls["n"] == 1, f"expected 1 OCR, got {ocr_calls['n']}"
        assert a.get("text") == b.get("text") == "ocr-text-once"
        assert b["source"] == png.name, b["source"]

        real_read = ce.read_pdf_pages
        reads = {"n": 0}

        def _counting_read(*args, **kwargs):
            reads["n"] += 1
            return real_read(*args, **kwargs)

        with patch.object(ce, "read_pdf_pages", side_effect=_counting_read):
            extract_from_source(str(pdf), memo=memo, attachment_id="att-a")
            extract_from_source(str(pdf), memo=memo, attachment_id="att-a")
            assert reads["n"] == 1, f"expected 1 read_pdf_pages, got {reads['n']}"

        # 2. Touch mtime → miss
        time.sleep(0.02)
        os.utime(pdf, None)
        with patch.object(ce, "read_pdf_pages", side_effect=_counting_read):
            reads["n"] = 0
            extract_from_source(str(pdf), memo=memo, attachment_id="att-a")
            assert reads["n"] == 1, "mtime change must miss cache"

        # 3. Different page_from / ocr_language → separate keys
        fp1 = fingerprint_for(
            pdf,
            page_from=1,
            page_to=1,
            page_limit=None,
            ocr_language="kor+eng",
            vision_all=False,
            char_limit=80_000,
            engine_probe=engine,
            kind="pdf",
        )
        fp2 = fingerprint_for(
            pdf,
            page_from=2,
            page_to=2,
            page_limit=None,
            ocr_language="kor+eng",
            vision_all=False,
            char_limit=80_000,
            engine_probe=engine,
            kind="pdf",
        )
        fp3 = fingerprint_for(
            pdf,
            page_from=1,
            page_to=1,
            page_limit=None,
            ocr_language="eng",
            vision_all=False,
            char_limit=80_000,
            engine_probe=engine,
            kind="pdf",
        )
        k1 = make_key(memo, fp1, attachment_id="att-a")
        k2 = make_key(memo, fp2, attachment_id="att-a")
        k3 = make_key(memo, fp3, attachment_id="att-a")
        assert k1.key_hash != k2.key_hash
        assert k1.key_hash != k3.key_hash

        # 4. invalidate(attachment_id=…) → next get None
        from iris.knowledge.extraction_cache import put

        put(memo, k1, {"kind": "pdf", "text": "x", "source": str(pdf.resolve())})
        assert get(memo, k1) is not None
        n = invalidate(memo, attachment_id="att-a")
        assert n >= 1
        assert get(memo, k1) is None

        # 5. Key JSON has no basename-only identity; same name different size → different hash
        other = root / "subdir"
        other.mkdir()
        pdf2 = other / "doc.pdf"
        _tiny_pdf(pdf2, "different size content body for key")
        # ensure sizes differ
        assert pdf.stat().st_size != pdf2.stat().st_size
        fa = fingerprint_for(
            pdf,
            page_from=None,
            page_to=None,
            page_limit=None,
            ocr_language="kor+eng",
            vision_all=False,
            char_limit=None,
            engine_probe=engine,
            kind="pdf",
        )
        fb = fingerprint_for(
            pdf2,
            page_from=None,
            page_to=None,
            page_limit=None,
            ocr_language="kor+eng",
            vision_all=False,
            char_limit=None,
            engine_probe=engine,
            kind="pdf",
        )
        ka = ExtractionCacheKey.build(memo.namespace, "", fa)
        kb = ExtractionCacheKey.build(memo.namespace, "", fb)
        assert ka.key_hash != kb.key_hash
        payload = json.dumps(fa.canonical(), sort_keys=True)
        assert "doc.pdf" not in payload
        assert pdf.name not in payload

        # vision_reader / vision_all → never put (skip cache)
        with patch.object(ce, "read_pdf_pages", side_effect=_counting_read):
            reads["n"] = 0
            extract_from_source(
                str(pdf),
                memo=memo,
                attachment_id="att-v",
                vision_reader=lambda pngs: "vision",
            )
            extract_from_source(
                str(pdf),
                memo=memo,
                attachment_id="att-v",
                vision_reader=lambda pngs: "vision",
            )
            assert reads["n"] == 2, "vision_reader must bypass cache"

        store.clear()
        assert len(memo._entries) == 0

    print("extraction_cache ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
