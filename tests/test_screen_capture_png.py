"""캡처 → PNG 변환, 특히 비전 모델 전송용 축소."""

from __future__ import annotations

import io
from unittest import TestCase

from iris.monitoring.screen_capture import CaptureResult, capture_result_to_png_bytes

try:
    from PIL import Image  # type: ignore

    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False


def _solid(width: int, height: int) -> CaptureResult:
    return CaptureResult(width, height, b"\x20\x40\x60" * (width * height))


class CaptureToPngTests(TestCase):
    def setUp(self) -> None:
        if not _HAS_PIL:
            self.skipTest("Pillow 미설치")

    def test_no_downscale_by_default(self) -> None:
        png = capture_result_to_png_bytes(_solid(300, 200))
        self.assertIsNotNone(png)
        assert png is not None
        self.assertEqual(Image.open(io.BytesIO(png)).size, (300, 200))

    def test_downscale_keeps_aspect_ratio(self) -> None:
        png = capture_result_to_png_bytes(_solid(2000, 1000), max_width=1024)
        assert png is not None
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1024, 512))

    def test_small_image_is_not_upscaled(self) -> None:
        png = capture_result_to_png_bytes(_solid(640, 480), max_width=1024)
        assert png is not None
        self.assertEqual(Image.open(io.BytesIO(png)).size, (640, 480))

    def test_extreme_aspect_ratio_keeps_at_least_one_pixel(self) -> None:
        """가로로 아주 긴 창에서 높이가 0으로 반올림되면 안 된다."""
        png = capture_result_to_png_bytes(_solid(4000, 3), max_width=100)
        assert png is not None
        w, h = Image.open(io.BytesIO(png)).size
        self.assertEqual(w, 100)
        self.assertGreaterEqual(h, 1)

    def test_bad_input_returns_none(self) -> None:
        self.assertIsNone(capture_result_to_png_bytes(CaptureResult(10, 10, b"short")))
