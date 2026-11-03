"""Lab PDF dump self-check: intent, parse→filename, hybrid write, reply has paths only.

  .venv\\Scripts\\python.exe -m iris.ui._check_lab_script_dump
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.lab_script_dump import (
    dump_lab_scripts,
    filename_for_label,
    format_lab_dump_reply,
    is_lab_dump_intent,
    parse_lab_programs,
    to_hermes_summary,
)


def _two_program_pdf(path: Path, *, junk: str = "UNRELATED_PAGE_OCR_DUMP_XYZ") -> None:
    import pymupdf

    fontfile = Path(r"C:\Windows\Fonts\malgun.ttf")
    fontname = "helv"
    doc = pymupdf.open()
    for label, code in (("프로그램 7-5", "print(5)"), ("프로그램 7-7", "print(7)")):
        page = doc.new_page(width=640, height=400)
        if fontfile.is_file():
            page.insert_font(fontname="malgun", fontfile=str(fontfile))
            fontname = "malgun"
        page.insert_text((72, 72), label, fontname=fontname)
        page.insert_text((72, 100), code, fontname="helv")
    page = doc.new_page(width=640, height=400)
    page.insert_text((72, 72), junk, fontname="helv")
    doc.save(str(path))
    doc.close()


def main() -> None:
    assert is_lab_dump_intent(
        "실습 스크립트 전부 만들어줘",
        [r"C:\fake\lecture.pdf"],
    )
    assert is_lab_dump_intent(
        "프로그램 7-5부터 전부 파일로",
        ["x.pdf"],
    )
    assert not is_lab_dump_intent("실습 설명해줘", ["x.pdf"])
    assert not is_lab_dump_intent("실습 스크립트 전부 만들어줘", [])
    assert not is_lab_dump_intent("이 pdf 위키에 저장해줘", ["x.pdf"])

    assert filename_for_label("프로그램 7-7") == "7-7.py"
    assert filename_for_label("7-5.py") == "7-5.py"
    assert filename_for_label("7-5") == "7-5.py"

    pages = [
        "[쪽 1]\n프로그램 7-5\nprint(1)\n",
        "[쪽 2]\n프로그램 7-7\nx = 1\n",
    ]
    programs = parse_lab_programs(pages)
    assert len(programs) == 2, programs
    assert programs[0].filename == filename_for_label(programs[0].label)
    assert programs[0].filename == "7-5.py"
    assert "print(1)" in programs[0].body
    assert programs[1].filename == "7-7.py"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "lecture.pdf"
        junk = "UNRELATED_PAGE_OCR_DUMP_XYZ"
        _two_program_pdf(pdf, junk=junk)
        result = dump_lab_scripts(pdf, root, out_subdir="labs")
        assert len(result.written) == 2, (result.written, result.errors)
        assert (root / "labs" / "7-5.py").is_file()
        assert (root / "labs" / "7-7.py").is_file()
        assert "print(5)" in (root / "labs" / "7-5.py").read_text(encoding="utf-8")
        assert "print(7)" in (root / "labs" / "7-7.py").read_text(encoding="utf-8")
        reply = format_lab_dump_reply(result)
        assert "labs/7-5.py" in reply.user_visible or "labs\\7-5.py" in reply.user_visible
        assert junk not in reply.user_visible
        assert "print(5)" not in reply.user_visible
        summary = to_hermes_summary(result)
        payload = summary.to_dict()
        assert "body" not in payload
        assert "text" not in payload
        assert junk not in str(payload)
        assert payload["count"] == 2

    print("lab_script_dump self-check ok")


if __name__ == "__main__":
    main()
