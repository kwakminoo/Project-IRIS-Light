"""Real lecture PDF dump contract (컴퓨터비전_08). Skip if file missing.

  .venv\\Scripts\\python.exe -m iris.knowledge._check_lab_dump_real_pdf
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.lab_script_dump import (
    dump_lab_scripts,
    extract_pdf_page_texts,
    resolve_lab_blocks,
)

# Measured path for 컴퓨터비전_08_백찬은.pdf (user machine).
_REAL_PDF = Path(
    r"C:\Users\kwakm\Desktop\동양미래대학교 2학년 2학기\컴퓨터비전\컴퓨터비전_08_백찬은.pdf"
)

_OLD_VAGUE = "라벨을 찾지 못했습니다"


def main() -> None:
    if not _REAL_PDF.is_file():
        print(f"skip: real PDF missing ({_REAL_PDF})")
        return

    pages, _trunc = extract_pdf_page_texts(_REAL_PDF, vision_reader=None)
    blocks, boundary_err = resolve_lab_blocks(pages)
    assert blocks, (
        f"expected ≥1 LabBlock from 08 PDF; boundary_err={boundary_err!r} pages={len(pages)}"
    )
    assert all((b.title or "").strip() for b in blocks), "every block needs a title"
    if boundary_err is not None:
        raise AssertionError(f"blocks present but boundary_err set: {boundary_err}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = dump_lab_scripts(
            _REAL_PDF, root, out_subdir="labs", vision_reader=None
        )
        err_blob = " ".join(result.errors)
        if not result.programs and err_blob:
            # no blocks → must mention 실습/segmenter, not only old vague line
            assert "실습" in err_blob or "segmenter" in err_blob.lower() or "세그" in err_blob
            assert err_blob.strip() != _OLD_VAGUE
            assert len(err_blob) > len(_OLD_VAGUE)

        empty_errs = [e for e in result.errors if "비어" in e or "empty" in e.lower()]
        written_n = len(result.written)
        block_n = len(result.programs)
        # Without vision, image-code labs may write 0 files; then block-level empty errors required.
        if written_n == 0:
            assert empty_errs or result.errors, (
                "zero written requires per-block empty-body (or other) errors, not silent fail"
            )
        for rel in result.written:
            assert (root / rel).is_file(), rel

        print(
            "lab_dump_real_pdf ok "
            f"blocks={block_n} written={written_n} "
            f"empty_body_errors={len(empty_errs)} errors={len(result.errors)} "
            f"titles={[b.title for b in blocks[:3]]}..."
        )
        if written_n == 0 and empty_errs:
            print(
                "note: no vision → empty bodies expected for image-only code; "
                "errors name empty body per file"
            )


if __name__ == "__main__":
    main()
