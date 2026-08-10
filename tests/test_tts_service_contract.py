"""
qwen-tts 호출 계약 테스트.

mock 모드에서는 실제 모델을 호출하지 않기 때문에, 시그니처가 어긋나도
런타임 전까지 드러나지 않는다. 여기서는 실제 qwen-tts와 동일한 시그니처를 가진
가짜 모델을 주입해 TTSService가 올바른 인자로 호출하는지 고정한다.
"""

from __future__ import annotations

import dataclasses
import math
import tempfile
import wave
from pathlib import Path
from unittest import TestCase, skipIf
from unittest.mock import patch

from services.voice_runtime import tts_service as tts_module
from services.voice_runtime.model_manager import VoiceModelManager
from services.voice_runtime.tts_service import (
    TTS_LANGUAGE,
    TTS_X_VECTOR_ONLY_MODE,
    TTSService,
)


MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
SAMPLE_RATE = 24000


class FakeQwen3TTSModel:
    """qwen_tts.Qwen3TTSModel과 동일한 시그니처만 흉내낸 가짜 모델."""

    def __init__(self) -> None:
        self.prepare_call: dict | None = None
        self.generate_call: dict | None = None

    def create_voice_clone_prompt(
        self,
        ref_audio,
        ref_text=None,
        x_vector_only_mode=False,
    ):
        self.prepare_call = {
            "ref_audio": ref_audio,
            "ref_text": ref_text,
            "x_vector_only_mode": x_vector_only_mode,
        }
        return [{"prompt": "fake"}]

    def generate_voice_clone(
        self,
        text,
        language=None,
        ref_audio=None,
        ref_text=None,
        x_vector_only_mode=False,
        voice_clone_prompt=None,
        non_streaming_mode=False,
        **kwargs,
    ):
        self.generate_call = {
            "text": text,
            "language": language,
            "x_vector_only_mode": x_vector_only_mode,
            "voice_clone_prompt": voice_clone_prompt,
            "kwargs": kwargs,
        }
        wav = [
            0.5 * math.sin(2.0 * math.pi * 220.0 * (i / SAMPLE_RATE))
            for i in range(SAMPLE_RATE)
        ]
        return ([wav], SAMPLE_RATE)


def _write_ref_wav(path: Path, seconds: float = 1.0) -> None:
    frames = int(seconds * 16000)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * frames)


class RealModeCallContractTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ref_path = self.root / "ref.wav"
        _write_ref_wav(self.ref_path)

        self.fake = FakeQwen3TTSModel()
        self.mm = VoiceModelManager()
        self.mm.set_tts(MODEL_NAME, self.fake)
        self.service = TTSService(self.mm)

        real_config = dataclasses.replace(tts_module.CONFIG, mock_mode=False)
        patcher = patch.object(tts_module, "CONFIG", real_config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _prepare(self):
        return self.service.prepare_voice_clone_prompt(
            ref_audio_path=str(self.ref_path),
            ref_text="안녕하세요 아이리스입니다",
            tts_model_name=MODEL_NAME,
        )

    def test_prepare_uses_ref_audio_and_x_vector_mode(self) -> None:
        self._prepare()
        call = self.fake.prepare_call
        self.assertIsNotNone(call)
        assert call is not None
        # ref_audio_path가 아니라 ref_audio
        self.assertEqual(call["ref_audio"], str(self.ref_path))
        self.assertIs(call["x_vector_only_mode"], TTS_X_VECTOR_ONLY_MODE)

    def test_generate_uses_lowercase_korean_and_prompt(self) -> None:
        prepared = self._prepare()
        out_dir = self.root / "generated"
        result = self.service.synthesize_speech(
            text="테스트 문장입니다",
            voice_prompt_hash=prepared.voice_prompt_hash,
            tts_model_name=MODEL_NAME,
            output_dir=out_dir,
        )

        call = self.fake.generate_call
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual(call["language"], "korean")
        self.assertEqual(call["language"], TTS_LANGUAGE)
        # 대문자면 발음이 깨진다 → 회귀 방지
        self.assertNotEqual(call["language"], "Korean")
        self.assertEqual(call["voice_clone_prompt"], [{"prompt": "fake"}])
        # output_dir은 qwen-tts 인자가 아니다 → 넘기면 TypeError
        self.assertNotIn("output_dir", call["kwargs"])

        out_path = Path(result.audio_path)
        self.assertTrue(out_path.is_file())
        with wave.open(str(out_path), "rb") as wf:
            self.assertEqual(wf.getframerate(), SAMPLE_RATE)
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getnframes(), SAMPLE_RATE)

    def test_prompt_hash_changes_with_mode(self) -> None:
        prepared = self._prepare()
        with patch.object(tts_module, "TTS_X_VECTOR_ONLY_MODE", not TTS_X_VECTOR_ONLY_MODE):
            other = TTSService(VoiceModelManager())._voice_prompt_hash(
                str(self.ref_path), "안녕하세요 아이리스입니다"
            )
        self.assertNotEqual(prepared.voice_prompt_hash, other)


def _qwen_tts_available() -> bool:
    try:
        import qwen_tts  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


@skipIf(not _qwen_tts_available(), "qwen-tts는 .venv-voice에만 설치됨")
class InstalledQwenTtsSignatureTests(TestCase):
    """실제 설치본이 있을 때만: 가짜 모델이 진짜 시그니처와 일치하는지 검증."""

    def test_signatures_match_fake(self) -> None:
        import inspect

        from qwen_tts import Qwen3TTSModel

        for name in ("create_voice_clone_prompt", "generate_voice_clone"):
            real = set(inspect.signature(getattr(Qwen3TTSModel, name)).parameters) - {"self"}
            fake = set(inspect.signature(getattr(FakeQwen3TTSModel, name)).parameters) - {"self"}
            self.assertEqual(real, fake, f"{name} 시그니처가 실제 qwen-tts와 다릅니다")
