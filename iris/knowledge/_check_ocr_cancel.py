"""OCR cancel mid-subprocess → EXTRACTION_CANCELLED + proc.kill.

Proves the existing `_ocr_cancelled` / cancelled callable path without
rewriting the OCR engine. A hanging Popen stand-in is cancelled on the
first communicate poll; the real kill + EXTRACTION_CANCELLED contract runs.

  .venv\\Scripts\\python.exe -m iris.knowledge._check_ocr_cancel
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from subprocess import TimeoutExpired
from threading import Event
from unittest.mock import patch


def _scanned_pdf(path: Path, label: str) -> None:
    from PIL import Image, ImageDraw

    import pymupdf

    img = Image.new("RGB", (480, 120), "white")
    ImageDraw.Draw(img).text((20, 40), label, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=480, height=120)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


class _HangProc:
    """OCR subprocess stand-in: communicate times out until kill."""

    def __init__(self, flip_cancel: Event, killed: list[bool]) -> None:
        self._flip = flip_cancel
        self._killed = killed
        self.returncode: int | None = None

    def __enter__(self) -> _HangProc:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        if self.returncode is not None:
            return b"", b""
        if timeout is not None:
            self._flip.set()
            raise TimeoutExpired(cmd=["tesseract"], timeout=timeout)
        return b"", b""

    def kill(self) -> None:
        self._killed.append(True)
        self.returncode = -9


def _check_mid_ocr_cancel_kills_subprocess() -> None:
    from iris.knowledge.content_extract import DocumentExtractionError, read_pdf_pages

    flip = Event()
    killed: list[bool] = []

    def cancelled() -> bool:
        return flip.is_set()

    def fake_popen(*_a, **_k):
        return _HangProc(flip, killed)

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        _scanned_pdf(pdf, "CANCEL_OCR_MARK")
        with (
            patch(
                "iris.knowledge.content_extract._ensure_tesseract",
                return_value=("tesseract", None, frozenset({"kor", "eng"})),
            ),
            patch("subprocess.Popen", side_effect=fake_popen),
        ):
            try:
                read_pdf_pages(pdf, cancelled=cancelled)
                raise AssertionError("expected EXTRACTION_CANCELLED")
            except DocumentExtractionError as exc:
                assert exc.code == "EXTRACTION_CANCELLED", exc.code
        assert killed, "OCR subprocess must be kill()'d on cancel"
        assert flip.is_set()


def _check_immediate_cancel_before_ocr() -> None:
    """cancelled() True before OCR starts → EXTRACTION_CANCELLED, no spawn."""
    from iris.knowledge.content_extract import DocumentExtractionError, read_pdf_pages

    spawned: list[bool] = []

    def fake_popen(*_a, **_k):
        spawned.append(True)
        raise AssertionError("Popen must not run when already cancelled")

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        _scanned_pdf(pdf, "PRECANCEL_MARK")
        with (
            patch(
                "iris.knowledge.content_extract._ensure_tesseract",
                return_value=("tesseract", None, frozenset({"kor", "eng"})),
            ),
            patch("subprocess.Popen", side_effect=fake_popen),
        ):
            try:
                read_pdf_pages(pdf, cancelled=lambda: True)
                raise AssertionError("expected EXTRACTION_CANCELLED")
            except DocumentExtractionError as exc:
                assert exc.code == "EXTRACTION_CANCELLED", exc.code
        assert not spawned, spawned


def main() -> None:
    _check_mid_ocr_cancel_kills_subprocess()
    _check_immediate_cancel_before_ocr()
    print("ocr_cancel self-check ok")


if __name__ == "__main__":
    main()
