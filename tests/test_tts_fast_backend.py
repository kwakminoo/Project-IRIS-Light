from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from services.voice_runtime.model_manager import PreparedVoiceClone, VoiceModelManager
from services.voice_runtime.config import _bounded_int_env
from services.voice_runtime.tts_service import TTSService
from services.voice_runtime import tts_stream as stream_mod
from services.voice_runtime.tts_stream import StreamSynthRequest, iter_pcm_chunks, warmup_faster_qwen


class _FakeFastModel:
    def __init__(self) -> None:
        self.warmup_calls = 0
        self.stream_calls: list[dict[str, object]] = []

    def warmup(self) -> None:
        self.warmup_calls += 1

    def generate_voice_clone_streaming(self, **kwargs: object):
        self.stream_calls.append(kwargs)
        yield [0.1, -0.1], 24000, {"ttfa_ms": 1}
        yield [0.2, -0.2], 24000, {}

    def generate_voice_clone(self, **kwargs: object):  # pragma: no cover - must never be used
        raise AssertionError("fast streaming path must not call generate_voice_clone")


class FastQwenStreamTests(TestCase):
    def setUp(self) -> None:
        self.manager = VoiceModelManager()
        self.service = TTSService(self.manager)
        self.prompt = object()
        self.manager.set_prepared_voice(PreparedVoiceClone("manual", self.prompt))
        self.config = SimpleNamespace(mock_mode=False, tts_stream_chunk_size=4)

    def test_fast_path_uses_streaming_and_preserves_prepared_prompt(self) -> None:
        fast = _FakeFastModel()
        req = StreamSynthRequest(text="실시간 음성입니다.", voice_prompt_hash="manual")
        with (
            patch.object(stream_mod, "CONFIG", self.config),
            patch.object(stream_mod, "_load_fast_model", return_value=fast),
        ):
            chunks = list(iter_pcm_chunks(self.service, req))

        self.assertEqual(fast.warmup_calls, 1)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(fast.stream_calls), 1)
        kwargs = fast.stream_calls[0]
        self.assertIs(kwargs["voice_clone_prompt"], self.prompt)
        self.assertEqual(kwargs["chunk_size"], 4)
        self.assertNotIn("ref_audio", kwargs)

    def test_fast_stream_rejects_whole_audio_result(self) -> None:
        def not_a_generator(**_: object) -> tuple[list[float], int]:
            return [0.1], 24000

        with self.assertRaisesRegex(RuntimeError, "non-streaming"):
            list(stream_mod._iter_fast_voice_clone_stream(not_a_generator))

    def test_stream_chunk_size_env_is_clamped(self) -> None:
        with patch.dict(os.environ, {"IRIS_TTS_STREAM_CHUNK_SIZE": "1"}):
            self.assertEqual(_bounded_int_env("IRIS_TTS_STREAM_CHUNK_SIZE", 4, minimum=2, maximum=8), 2)
        with patch.dict(os.environ, {"IRIS_TTS_STREAM_CHUNK_SIZE": "99"}):
            self.assertEqual(_bounded_int_env("IRIS_TTS_STREAM_CHUNK_SIZE", 4, minimum=2, maximum=8), 8)
        with patch.dict(os.environ, {"IRIS_TTS_STREAM_CHUNK_SIZE": "invalid"}):
            self.assertEqual(_bounded_int_env("IRIS_TTS_STREAM_CHUNK_SIZE", 4, minimum=2, maximum=8), 4)

    def test_model_manager_loads_each_key_once(self) -> None:
        loads: list[object] = []
        model = object()

        def load() -> object:
            loads.append(model)
            return model

        self.assertIs(self.manager.get_or_load_tts("fast:test", load), model)
        self.assertIs(self.manager.get_or_load_tts("fast:test", load), model)
        self.assertEqual(loads, [model])

    def test_warmup_reports_loaded_warmed_fast_backend(self) -> None:
        fast = _FakeFastModel()
        self.manager.set_tts("fast:Qwen/test", fast)
        with (
            patch.object(stream_mod, "CONFIG", self.config),
            patch.object(stream_mod, "_load_fast_model", return_value=fast),
            patch.object(stream_mod, "faster_qwen_available", return_value=True),
        ):
            status = warmup_faster_qwen(self.service, "Qwen/test")

        self.assertEqual(fast.warmup_calls, 1)
        self.assertTrue(status["faster_qwen"])
        self.assertTrue(status["fast_model_loaded"])
        self.assertTrue(status["fast_model_warmed"])
        self.assertEqual(status["stream_backend"], "faster_qwen3_tts")
