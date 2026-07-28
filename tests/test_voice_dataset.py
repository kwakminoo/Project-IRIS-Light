from __future__ import annotations

import json
import math
import tempfile
import wave
from pathlib import Path
from unittest import TestCase

from services.voice_runtime.voice_dataset import (
    analyze_voice_file,
    discover_audio_files,
    quality_score,
    recommend_reference_samples,
    write_manifest,
)


def _write_wav(path: Path, *, seconds: float = 1.0, sample_rate: int = 16000) -> None:
    import struct

    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()
        for i in range(frames):
            value = int(12000 * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))
            data.extend(struct.pack("<h", value))
        wf.writeframes(bytes(data))


class VoiceDatasetTests(TestCase):
    def test_recursive_discovery_and_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            _write_wav(nested / "one.wav")
            (nested / "two.txt").write_text("x", encoding="utf-8")
            (root / "three.mp3").write_bytes(b"fake")
            files = discover_audio_files(root)
            self.assertEqual({p.suffix for p in files}, {".wav", ".mp3"})

    def test_analyze_wav_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.wav"
            _write_wav(path, seconds=8.0)
            item = analyze_voice_file(path, transcript="안녕하세요", language="ko", language_probability=0.99)
            self.assertTrue(item.readable)
            self.assertGreater(item.duration, 7.5)
            self.assertGreater(item.sample_rate, 0)
            self.assertGreater(item.quality_score, 70.0)

    def test_reference_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for idx, seconds in enumerate((3.0, 9.0, 13.0, 20.0)):
                p = Path(td) / f"s{idx}.wav"
                _write_wav(p, seconds=seconds)
                paths.append(p)
            items = [
                analyze_voice_file(p, transcript="문장", language="ko", language_probability=0.98)
                for p in paths
            ]
            picks = recommend_reference_samples(items, top_k=2)
            self.assertEqual(len(picks), 2)
            self.assertTrue(all(x.language == "ko" for x in picks))

    def test_manifest_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.wav"
            _write_wav(path, seconds=6.0)
            item = analyze_voice_file(path, transcript="테스트", language="ko", language_probability=0.95)
            jsonl = Path(td) / "manifest.jsonl"
            csvp = Path(td) / "manifest.csv"
            write_manifest([item], jsonl_path=jsonl, csv_path=csvp)
            self.assertTrue(jsonl.is_file())
            self.assertTrue(csvp.is_file())
            row = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["transcript"], "테스트")

