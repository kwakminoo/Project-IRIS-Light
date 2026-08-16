"""프로필 경로 라우팅 계약 — mock 모드라 실제 모델을 부르지 않는다."""

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("VOICE_RUNTIME_MOCK", "1")

from services.voice_runtime.model_manager import VoiceModelManager  # noqa: E402
from services.voice_runtime.tone_router import (  # noqa: E402
    TONE_BRIEFING,
    TONE_CAUTION,
    TONE_NEUTRAL,
    TONE_NUMERIC,
    TONE_QUESTION,
)
from services.voice_runtime.tts_service import (  # noqa: E402
    PROFILE_PROMPT_PREFIX,
    TTSService,
)
from services.voice_runtime.voice_profile import ToneReference, VoiceProfile  # noqa: E402


def _service_with_profile(tones=(TONE_NEUTRAL, TONE_QUESTION, TONE_CAUTION, TONE_BRIEFING, TONE_NUMERIC)):
    service = TTSService(VoiceModelManager())
    rng = np.random.default_rng(3)
    service._profile = VoiceProfile(
        name="fixture",
        model_name="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        base_x_vector=rng.normal(size=8).astype(np.float32),
        tones={
            tone: ToneReference(
                tone=tone,
                x_vector=rng.normal(size=8).astype(np.float32),
                ref_code=None,
                ref_text="",
                source_file="",
                sample_count=5,
            )
            for tone in tones
        },
    )
    service._profile_loaded = True
    return service


@pytest.fixture()
def out_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def _speak(service, text, out_dir, tone=None, voice_prompt_hash=""):
    return service.synthesize_speech(
        text=text,
        voice_prompt_hash=voice_prompt_hash,
        tts_model_name="dummy",
        output_dir=out_dir,
        tone=tone,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("회의실 예약을 완료했습니다.", TONE_NEUTRAL),
        ("지금 바로 보낼까요?", TONE_QUESTION),
        ("이 작업은 파일을 삭제합니다.", TONE_CAUTION),
        ("오늘 확인할 항목은 세 가지입니다.", TONE_BRIEFING),
        ("오전 아홉 시 십이 분, 메일 17통입니다.", TONE_NUMERIC),
    ],
)
def test_empty_hash_routes_by_text(text, expected, out_dir):
    result = _speak(_service_with_profile(), text, out_dir)
    assert result.tone == expected


def test_explicit_tone_overrides_classification(out_dir):
    result = _speak(_service_with_profile(), "회의실 예약을 완료했습니다.", out_dir, tone=TONE_CAUTION)
    assert result.tone == TONE_CAUTION


def test_unknown_tone_falls_back_to_neutral(out_dir):
    result = _speak(_service_with_profile(), "회의실 예약을 완료했습니다.", out_dir, tone="없는톤")
    assert result.tone == TONE_NEUTRAL


def test_tone_missing_from_profile_falls_back_to_neutral(out_dir):
    # narration 톤이 없는 프로필에서 긴 문장을 넣어도 깨지지 않아야 한다.
    service = _service_with_profile(tones=(TONE_NEUTRAL,))
    result = _speak(service, "오전 업무 시작을 돕겠습니다. " * 10, out_dir)
    assert result.tone == TONE_NEUTRAL


def test_prompt_hash_differs_per_tone():
    service = _service_with_profile()
    hashes = {service.profile_prompt_hash(t) for t in (TONE_NEUTRAL, TONE_CAUTION, TONE_QUESTION)}
    assert len(hashes) == 3, "톤별 해시가 겹치면 생성 캐시가 섞인다"
    assert all(h.startswith(f"{PROFILE_PROMPT_PREFIX}:") for h in hashes)


def test_different_tones_write_different_files(out_dir):
    service = _service_with_profile()
    text = "회의실 예약을 완료했습니다."
    a = _speak(service, text, out_dir, tone=TONE_NEUTRAL)
    b = _speak(service, text, out_dir, tone=TONE_CAUTION)
    assert a.audio_path != b.audio_path


def test_profile_hash_is_accepted_as_input(out_dir):
    service = _service_with_profile()
    result = _speak(service, "지금 보낼까요?", out_dir, voice_prompt_hash=service.profile_prompt_hash(TONE_NEUTRAL))
    # profile: 해시로 들어와도 프로필 경로를 타고, 톤은 텍스트에서 다시 정해진다.
    assert result.tone == TONE_QUESTION


def test_manual_hash_bypasses_profile(out_dir):
    # profile: 접두사가 없는 해시는 수동 경로다 → 톤 라우팅이 일어나지 않는다.
    result = _speak(_service_with_profile(), "지금 보낼까요?", out_dir, voice_prompt_hash="manual-abc")
    assert result.tone == ""


def test_no_profile_requires_manual_hash(out_dir):
    service = TTSService(VoiceModelManager())
    service._profile = None
    service._profile_loaded = True
    with pytest.raises(RuntimeError):
        _speak(service, "안녕하세요", out_dir)


def test_empty_text_is_rejected(out_dir):
    with pytest.raises(RuntimeError):
        _speak(_service_with_profile(), "   ", out_dir)
