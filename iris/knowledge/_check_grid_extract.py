"""P1 grid_extract 자검 — 픽스처에서 전경·십자 커널 JSON 재현."""

from __future__ import annotations

import tempfile
from pathlib import Path


def _assert_image_grid(data: list[list[int]]) -> None:
    assert len(data) == 5 and all(len(r) == 5 for r in data), data
    for r in range(5):
        for c in range(5):
            expect = 1 if 1 <= r <= 3 and 1 <= c <= 3 else 0
            assert data[r][c] == expect, (r, c, data)


def _assert_kernel(data: list[list[int]]) -> None:
    assert len(data) == 3 and all(len(r) == 3 for r in data), data
    expect = [
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0],
    ]
    assert data == expect, data


def main() -> int:
    from iris.knowledge.grid_extract import (
        extract_binary_grid,
        extract_binary_grid_verdict,
        format_grid_attachment_text,
        write_morphology_fixture,
        write_noisy_multi_grid_fixture,
    )
    from iris.runtime.attachment_context import _ocr_image

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "morph.png"
        write_morphology_fixture(path)
        parsed = extract_binary_grid(path)
        assert parsed is not None, "extract_binary_grid returned None"
        by_name = {g["name"]: g["data"] for g in parsed["grids"]}
        assert "image" in by_name and "kernel" in by_name, by_name.keys()
        _assert_image_grid(by_name["image"])
        _assert_kernel(by_name["kernel"])
        assert not any(n.startswith("grid") for n in by_name), by_name.keys()
        verdict = extract_binary_grid_verdict(path)
        assert verdict.ok and verdict.score >= 0.55, verdict

        text = format_grid_attachment_text(parsed)
        assert "STRUCTURED BINARY GRID" in text
        assert "```matrix" in text
        assert "0 1 1 1 0" in text
        assert "0 1 0" in text

        ocr_text = _ocr_image(path)
        assert "STRUCTURED BINARY GRID" in ocr_text, ocr_text[:200]
        assert "```matrix" in ocr_text

        # 잡음 다수 grids → None 또는 image/kernel만 (gridN 나열 금지)
        noisy = Path(tmp) / "noisy.png"
        write_noisy_multi_grid_fixture(noisy)
        noisy_parsed = extract_binary_grid(noisy)
        if noisy_parsed is not None:
            names = [g.get("name") for g in noisy_parsed.get("grids") or []]
            assert len(names) <= 3, names
            assert not any(str(n).startswith("grid") for n in names), names
        else:
            assert not extract_binary_grid_verdict(noisy).ok

    print("grid_extract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
