"""채팅 자료 발췌 self-check.

  .venv\\Scripts\\python.exe -m iris.ui._check_material_excerpt
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from iris.knowledge.content_extract import read_pdf_pages
from iris.knowledge.material_excerpt import (
    build_material_block,
    turn_should_read_materials,
)
from iris.ui.chat.at_path_refs import extract_at_path_refs


def _scanned_pdf(path: Path) -> None:
    from PIL import Image, ImageDraw

    import pymupdf

    img = Image.new("RGB", (480, 120), "white")
    ImageDraw.Draw(img).text((20, 40), "SCAN", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=480, height=120)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _text_pdf(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Data structures store and retrieve records. Stack and queue are basic structures.",
    )
    doc.save(str(path))
    doc.close()


def _docx(path: Path, text: str) -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def main() -> None:
    assert turn_should_read_materials("이 대화를 PDF로 저장해 줘", []) is False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "Downloads"
        folder.mkdir()
        named = folder / "01_자료구조의 이해.txt"
        named.write_text("스택과 큐", encoding="utf-8")
        full = f"@{(folder / '01_자료구조의 이해.txt').as_posix()} 파악해 줘"
        refs = extract_at_path_refs(full)
        assert refs and refs[0].endswith("01_자료구조의 이해.txt"), refs
        block = build_material_block(full, [])
        assert "스택과 큐" in block, block

        prefix = f"@{(folder / '01_자료구조의').as_posix()} 설명해 줘"
        prefixed = build_material_block(prefix, [])
        assert "스택과 큐" in prefixed, prefixed

        (folder / "01_자료구조의 해설.txt").write_text("해설본문", encoding="utf-8")
        many = build_material_block(prefix, [])
        assert "스택과 큐" not in many and "해설본문" not in many, many
        assert "01_자료구조의 이해.txt" in many and "01_자료구조의 해설.txt" in many

        pack = root / "pack"
        pack.mkdir()
        (pack / "note.txt").write_text("보이는본문", encoding="utf-8")
        nested = pack / "nested"
        nested.mkdir()
        (nested / "secret.txt").write_text("숨김본문", encoding="utf-8")
        folder_block = build_material_block("폴더", [str(pack)])
        assert "보이는본문" in folder_block, folder_block
        assert "숨김본문" not in folder_block
        assert "nested/" in folder_block

        script = root / "hello.py"
        script.write_text("print('파이썬본문')\n", encoding="utf-8")
        assert "파이썬본문" in build_material_block("코드", [str(script)])

        doc = root / "note.docx"
        _docx(doc, "오피스본문")
        assert "오피스본문" in build_material_block("문서", [str(doc)])

        hwp = root / "note.hwp"
        hwp.write_bytes(b"hwp")
        assert "한글(HWP)" in build_material_block("한글", [str(hwp)])

        long = root / "long.txt"
        long.write_text("가" * 13_000, encoding="utf-8")
        long_block = build_material_block("길어", [str(long)])
        assert "가" * 13_000 in long_block
        assert "잘림: 채팅 발췌 상한에서 끊었습니다." not in long_block

        import iris.knowledge.content_extract as content_extract

        original_fetch = content_extract.fetch_url_text
        content_extract.fetch_url_text = lambda url, timeout=20.0: ("예시", "페이지글자")
        try:
            url_block = build_material_block("https://example.com/a 파악해 줘", [])
        finally:
            content_extract.fetch_url_text = original_fetch
        assert "페이지글자" in url_block, url_block

        scanned = root / "scan.pdf"
        _scanned_pdf(scanned)
        original_ocr = content_extract._ocr_png_bytes
        content_extract._ocr_png_bytes = lambda png: ("", "tesseract missing")
        try:
            scanned_data = read_pdf_pages(
                scanned,
                vision_reader=lambda pngs: "스캔된 자료구조 설명입니다",
            )
        finally:
            content_extract._ocr_png_bytes = original_ocr
        assert scanned_data["vision_used"] is True
        assert "스캔된 자료구조" in str(scanned_data["text"])

        text_pdf = root / "text.pdf"
        _text_pdf(text_pdf)
        called = {"n": 0}

        def _vision(pngs: list[bytes]) -> str:
            called["n"] += 1
            return "vision should not run here"

        text_data = read_pdf_pages(text_pdf, vision_reader=_vision)
        assert called["n"] == 0, text_data
        assert "Stack and queue" in str(text_data["text"])

    print("material_excerpt self-check ok")


if __name__ == "__main__":
    main()
