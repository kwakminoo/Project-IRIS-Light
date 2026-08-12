import tempfile
from pathlib import Path

import numpy as np
import pytest

from services.voice_runtime.tone_router import TONE_NEUTRAL, TONE_QUESTION
from services.voice_runtime.voice_profile import (
    ToneReference,
    VoiceProfile,
    average_embeddings,
    default_profile_paths,
    load_default_profile,
    most_central_index,
)


def _profile() -> VoiceProfile:
    rng = np.random.default_rng(7)
    return VoiceProfile(
        name="test",
        model_name="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        base_x_vector=rng.normal(size=16).astype(np.float32),
        tones={
            TONE_NEUTRAL: ToneReference(
                tone=TONE_NEUTRAL,
                x_vector=rng.normal(size=16).astype(np.float32),
                ref_code=rng.integers(0, 500, size=(12, 4)).astype(np.int32),
                ref_text="회의실 예약을 완료했습니다.",
                source_file="E/회의실.m4a",
                sample_count=35,
                ref_duration=12.0,
            ),
            TONE_QUESTION: ToneReference(
                tone=TONE_QUESTION,
                x_vector=rng.normal(size=16).astype(np.float32),
                ref_code=None,
                ref_text="",
                source_file="",
                sample_count=25,
            ),
        },
        meta={"sample_used": 150},
    )


def test_save_load_roundtrip():
    original = _profile()
    with tempfile.TemporaryDirectory() as td:
        npz = Path(td) / "p.npz"
        original.save(npz)
        loaded = VoiceProfile.load(npz)

    assert loaded.name == original.name
    assert loaded.model_name == original.model_name
    assert loaded.dim == 16
    assert loaded.meta["sample_used"] == 150
    np.testing.assert_allclose(loaded.base_x_vector, original.base_x_vector, rtol=1e-6)

    neutral = loaded.tones[TONE_NEUTRAL]
    assert neutral.ref_text == "회의실 예약을 완료했습니다."
    assert neutral.sample_count == 35
    assert neutral.supports_icl
    np.testing.assert_array_equal(neutral.ref_code, original.tones[TONE_NEUTRAL].ref_code)


def test_tone_without_ref_code_does_not_support_icl():
    loaded_tone = _profile().tones[TONE_QUESTION]
    assert loaded_tone.ref_code is None
    assert not loaded_tone.supports_icl


def test_x_vector_for_unknown_tone_falls_back_to_base():
    profile = _profile()
    np.testing.assert_allclose(profile.x_vector_for("없는톤"), profile.base_x_vector)
    np.testing.assert_allclose(profile.x_vector_for(None), profile.base_x_vector)


def test_tone_reference_returns_none_for_unknown_tone():
    assert _profile().tone_reference("없는톤") is None


def test_average_embeddings_drops_outlier():
    base = np.ones(8, dtype=np.float32)
    vectors = [base + np.random.default_rng(i).normal(scale=0.01, size=8) for i in range(10)]
    vectors.append(-base * 5.0)  # 반대 방향 이상치

    mean, kept = average_embeddings(vectors, outlier_z=1.5)
    assert len(vectors) - 1 not in kept, "이상치가 평균에 남았습니다"
    assert float(np.dot(mean, base)) > 0


def test_average_embeddings_keeps_all_when_uniform():
    vectors = [np.ones(4, dtype=np.float32) for _ in range(5)]
    _mean, kept = average_embeddings(vectors)
    assert len(kept) == 5


def test_average_embeddings_rejects_empty():
    with pytest.raises(ValueError):
        average_embeddings([])


def test_most_central_index_picks_cluster_member():
    cluster = [np.array([1.0, 0.0], dtype=np.float32) for _ in range(4)]
    outlier = np.array([0.0, 1.0], dtype=np.float32)
    assert most_central_index([*cluster, outlier]) < 4


def test_missing_profile_files_raise():
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(FileNotFoundError):
            VoiceProfile.load(Path(td) / "nope.npz")


def test_committed_profile_loads_and_matches_tones():
    """저장소에 커밋된 프로필이 실제로 읽히는지 — PR 산출물의 계약."""
    npz_path, json_path = default_profile_paths()
    if not npz_path.is_file():
        pytest.skip("보이스 프로필이 아직 빌드되지 않았습니다.")

    profile = load_default_profile()
    assert profile is not None
    assert profile.dim > 0
    assert json_path.is_file()
    assert TONE_NEUTRAL in profile.tones, "기본 폴백 톤이 없으면 런타임이 깨집니다."
    for tone, ref in profile.tones.items():
        assert ref.x_vector.shape == (profile.dim,), f"{tone} 임베딩 차원 불일치"
        assert ref.sample_count > 0
        if ref.ref_code is not None:
            assert ref.ref_code.ndim == 2
