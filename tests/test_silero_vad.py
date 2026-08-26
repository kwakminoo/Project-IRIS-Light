"""Silero VAD 설치/다운로드/스코어."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from iris.audio.silero_vad import SileroVad, ensure_onnxruntime


class _FakeHttp:
    def __enter__(self) -> "_FakeHttp":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"onnx-bytes" * 2000


class SileroVadTests(TestCase):
    def test_ensure_onnxruntime_imports(self) -> None:
        self.assertTrue(ensure_onnxruntime())

    def test_download_writes_cache_file(self) -> None:
        vad = SileroVad(score_fn=lambda _w: 0.0)
        with TemporaryDirectory() as td:
            path = Path(td) / "silero_vad.onnx"
            with patch("iris.audio.silero_vad.urlopen", return_value=_FakeHttp()):
                vad._download(path)
            self.assertGreaterEqual(path.stat().st_size, 10_000)

    def test_skip_pip_env_does_not_crash(self) -> None:
        with patch.dict(os.environ, {"IRIS_SKIP_ORT_INSTALL": "1"}):
            self.assertTrue(ensure_onnxruntime())

    def test_real_model_scores_when_cached(self) -> None:
        vad = SileroVad(load_async=False)
        if not vad.available:
            self.skipTest("Silero ONNX not loaded")
        silence = np.zeros(1600, dtype=np.int16).tobytes()
        p_sil = vad.speech_prob(silence)
        self.assertGreaterEqual(p_sil, 0.0)
        self.assertLessEqual(p_sil, 1.0)
