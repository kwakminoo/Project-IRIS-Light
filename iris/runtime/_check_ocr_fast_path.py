"""Image extract tries local OCR before vision LLM."""

from __future__ import annotations

import inspect

from iris.runtime import attachment_context as ac


def main() -> None:
    src = inspect.getsource(ac._ocr_image)
    i_ocr = src.index("_ocr_png_bytes")
    i_reader = src.index("_image_reader.get")
    assert i_ocr < i_reader, "local OCR must run before vision reader"
    print("ocr fast path ok")


if __name__ == "__main__":
    main()
