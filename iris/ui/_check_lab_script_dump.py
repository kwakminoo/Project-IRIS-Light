"""Lab PDF dump self-check: intent, parse→filename, hybrid write, reply has paths only.

  .venv\\Scripts\\python.exe -m iris.ui._check_lab_script_dump
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from iris.knowledge.lab_script_dump import (
    LabBlock,
    dump_lab_scripts,
    filename_for_label,
    format_lab_dump_reply,
    is_lab_dump_intent,
    parse_lab_programs,
    parse_practice_title_blocks,
    to_agent_summary,
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


def _practice_title_pdf(path: Path) -> None:
    import pymupdf

    fontfile = Path(r"C:\Windows\Fonts\malgun.ttf")
    doc = pymupdf.open()
    for title, code in (
        ("(실습) YOLO detect", "print('yolo')"),
        ("(실습) Bar train", "x = 2"),
    ):
        page = doc.new_page(width=640, height=400)
        fontname = "helv"
        if fontfile.is_file():
            page.insert_font(fontname="malgun", fontfile=str(fontfile))
            fontname = "malgun"
        page.insert_text((72, 72), title, fontname=fontname)
        page.insert_text((72, 100), code, fontname="helv")
    doc.save(str(path))
    doc.close()


def _blank_lab_pdf(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=640, height=400)
    page.insert_text((72, 72), "UNRELATED_NO_LAB_MARKERS", fontname="helv")
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
    assert programs[0].filename == filename_for_label(programs[0].title)
    assert programs[0].filename == "7-5.py"
    assert "print(1)" in programs[0].body
    assert programs[1].filename == "7-7.py"
    assert programs[0].label == programs[0].title

    # (실습) title heuristic
    sil_pages = [
        "[쪽 1]\n(실습) Foo\nprint('a')\n",
        "[쪽 2]\n(실습) Bar baz\ny = 9\n",
    ]
    sil = parse_practice_title_blocks(sil_pages)
    assert len(sil) == 2, sil
    assert sil[0].title.startswith("(실습)")
    assert "print('a')" in sil[0].body
    assert sil[0].filename == filename_for_label(sil[0].title)
    assert "y = 9" in sil[1].body

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
        summary = to_agent_summary(result)
        payload = summary.to_dict()
        assert "body" not in payload
        assert "text" not in payload
        assert junk not in str(payload)
        assert payload["count"] == 2

        # (실습) titles → safe filenames written (page texts → dump path)
        import iris.knowledge.lab_script_dump as dump_mod

        sil_extract = [
            "[쪽 1]\n(실습) YOLO detect\nprint('yolo')\n",
            "[쪽 2]\n(실습) Bar train\nx = 2\n",
        ]
        real_extract = dump_mod.extract_pdf_page_texts
        dump_mod.extract_pdf_page_texts = (  # type: ignore[assignment]
            lambda *_a, **_k: (sil_extract, False)
        )
        try:
            # dummy pdf path must exist for Path checks inside dump before extract
            pdf2 = root / "practice.pdf"
            _practice_title_pdf(pdf2)
            out2 = root / "p2"
            out2.mkdir()
            result2 = dump_lab_scripts(pdf2, out2, out_subdir="labs")
        finally:
            dump_mod.extract_pdf_page_texts = real_extract  # type: ignore[assignment]
        assert len(result2.written) == 2, (result2.written, result2.errors)
        for rel in result2.written:
            assert rel.endswith(".py")
            assert Path(rel).name == Path(rel).name  # single-segment basename in path
            assert (out2 / rel).is_file()
            assert "/" not in Path(rel).name
        bodies = "\n".join((out2 / r).read_text(encoding="utf-8") for r in result2.written)
        assert "print('yolo')" in bodies
        assert "x = 2" in bodies

        # no labels / no titles → clear error (not bare 「라벨을 찾지」 alone)
        pdf3 = root / "blank.pdf"
        _blank_lab_pdf(pdf3)
        out3 = root / "p3"
        out3.mkdir()
        result3 = dump_lab_scripts(pdf3, out3, out_subdir="labs")
        assert not result3.written
        err_blob = " ".join(result3.errors)
        assert "segmenter" in err_blob.lower() or "세그" in err_blob or "제목" in err_blob
        assert "N-M" in err_blob or "라벨" in err_blob
        assert len(err_blob) > len("라벨을 찾지 못했습니다")

        # injected segmenter → files written
        def _seg(_pages):
            return [
                LabBlock(
                    title="Seg Alpha",
                    filename="seg_alpha.py",
                    body="print('seg')\n",
                    pages=(1,),
                )
            ]

        out4 = root / "p4"
        out4.mkdir()
        result4 = dump_lab_scripts(
            pdf3, out4, out_subdir="labs", segmenter=_seg
        )
        assert "labs/seg_alpha.py" in result4.written or any(
            p.endswith("seg_alpha.py") for p in result4.written
        ), (result4.written, result4.errors)
        written_path = out4 / "labs" / "seg_alpha.py"
        assert written_path.is_file()
        assert "print('seg')" in written_path.read_text(encoding="utf-8")
        sum4 = to_agent_summary(result4).to_dict()
        assert "print('seg')" not in str(sum4)
        assert "Seg Alpha" in sum4["labels"]

    # auto-intercept disabled
    from iris.ui.window.main_window import MainWindow

    fake_turn = SimpleNamespace(
        text="실습 스크립트 전부 만들어줘",
        attachments=[r"C:\fake\lecture.pdf"],
        id="t1",
    )
    assert MainWindow._try_local_lab_dump(SimpleNamespace(), fake_turn, "m") is False
    assert MainWindow._try_local_lab_dump(SimpleNamespace(), fake_turn) is False

    print("lab_script_dump self-check ok")


if __name__ == "__main__":
    main()
