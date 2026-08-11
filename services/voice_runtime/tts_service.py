from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CONFIG
from .model_manager import PreparedVoiceClone, VoiceModelManager

# qwen-tts는 language 문자열을 프로세서 프롬프트에 그대로 넣는다.
# "Korean"(대문자)로 주면 발음이 깨지므로 반드시 소문자로 고정한다.
TTS_LANGUAGE = "korean"

# x_vector_only_mode=True: 화자 임베딩만 사용 (ref_text 무시).
# ICL 모드(False)는 ref_text가 기준 음성과 정확히 일치해야 해서 불안정하다.
TTS_X_VECTOR_ONLY_MODE = True


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _pcm16_bytes(wav: Any) -> bytes:
    """float 파형(-1..1)을 16bit PCM 리틀엔디안 바이트로 변환. numpy는 있으면 사용."""
    try:
        import numpy as np

        data = np.asarray(wav, dtype="float32").reshape(-1)
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        if peak > 1.0:
            data = data / peak
        return (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    except ImportError:
        pass

    import array

    samples = [float(x) for x in wav]
    peak = max((abs(x) for x in samples), default=0.0)
    scale = 1.0 / peak if peak > 1.0 else 1.0
    pcm = array.array(
        "h",
        (int(max(-1.0, min(1.0, x * scale)) * 32767.0) for x in samples),
    )
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm.tobytes()


def _write_wav(path: Path, wav: Any, sample_rate: int) -> None:
    """generate_voice_clone이 돌려준 float 파형을 16bit PCM wav로 저장."""
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(_pcm16_bytes(wav))


def _silence_wav_bytes(seconds: float = 1.0, sample_rate: int = 22050) -> bytes:
    import struct
    import wave

    n_frames = max(1, int(seconds * sample_rate))
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name

    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            silence = struct.pack("<h", 0)
            wf.writeframes(silence * n_frames)
        return Path(path).read_bytes()
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def clear_generated_audio_cache(
    output_dir: Path | None = None,
    *,
    max_age_sec: float = 7 * 24 * 3600,
) -> int:
    """오래된 생성 음성 파일 삭제. 삭제 개수 반환."""
    target = output_dir or (CONFIG.iris_home_dir / "audio" / "generated")
    if not target.is_dir():
        return 0
    now = time.time()
    removed = 0
    for path in target.glob("*.wav"):
        try:
            if now - path.stat().st_mtime > max_age_sec:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


@dataclass(frozen=True)
class SpeechResult:
    audio_path: str
    text: str


class TTSService:
    """
    Qwen3-TTS zero-shot voice cloning (voice_prompt 준비 → 생성).

    - GUI 스레드 로딩 금지: 이 서비스 안에서만 lazy load
    - ref_audio/ref_text가 바뀌면 voice_prompt_hash 변경 → 캐시 재생성
    """

    def __init__(self, model_manager: VoiceModelManager) -> None:
        self._mm = model_manager

    def _get_tts_model_key(self, model_name: str) -> str:
        return model_name

    def _ensure_tts_model(self, model_name: str) -> Any:
        key = self._get_tts_model_key(model_name)
        existing = self._mm.get_tts(key)
        if existing is not None:
            return existing

        try:
            from qwen_tts import Qwen3TTSModel  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "qwen-tts가 설치되지 않았습니다. "
                "scripts/setup_voice_runtime 으로 .venv-voice를 구성하세요."
            ) from exc

        # fp16은 CUDA device-side assert로 죽는다. GPU에서는 bf16 고정.
        load_kwargs: dict[str, Any] = {}
        try:
            import torch

            if torch.cuda.is_available():
                load_kwargs = {"device_map": "cuda:0", "dtype": torch.bfloat16}
            else:
                load_kwargs = {"device_map": "cpu", "dtype": torch.float32}
        except Exception:  # noqa: BLE001
            load_kwargs = {}

        try:
            model = Qwen3TTSModel.from_pretrained(model_name, **load_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"TTS 모델 로딩 실패 ({model_name}): {exc}") from exc
        self._mm.set_tts(key, model)
        return model

    def _voice_prompt_hash(self, ref_audio_path: str, ref_text: str) -> str:
        mode = "xvec" if TTS_X_VECTOR_ONLY_MODE else "icl"
        return _sha256_text(f"{ref_audio_path}::{ref_text}::{mode}")

    def prepare_voice_clone_prompt(
        self,
        *,
        ref_audio_path: str,
        ref_text: str,
        tts_model_name: str,
        voice_prompt_hash: str | None = None,
    ) -> PreparedVoiceClone:
        ref_path = Path(ref_audio_path)
        if not ref_path.is_file():
            raise RuntimeError(f"기준 음성 파일이 없습니다: {ref_audio_path}")
        if not (ref_text or "").strip():
            raise RuntimeError("기준 대본(ref_text)이 비어 있습니다.")

        if not voice_prompt_hash:
            voice_prompt_hash = self._voice_prompt_hash(ref_audio_path, ref_text)

        cached = self._mm.get_prepared_voice(voice_prompt_hash)
        if cached is not None:
            return cached

        if CONFIG.mock_mode:
            prepared = PreparedVoiceClone(
                voice_prompt_hash=voice_prompt_hash, voice_clone_prompt={"mock": True}
            )
            self._mm.set_prepared_voice(prepared)
            return prepared

        tts_model = self._ensure_tts_model(tts_model_name)
        prompt = tts_model.create_voice_clone_prompt(
            ref_audio=ref_audio_path,
            ref_text=ref_text,
            x_vector_only_mode=TTS_X_VECTOR_ONLY_MODE,
        )
        prepared = PreparedVoiceClone(
            voice_prompt_hash=voice_prompt_hash, voice_clone_prompt=prompt
        )
        self._mm.set_prepared_voice(prepared)
        return prepared

    def synthesize_speech(
        self,
        *,
        text: str,
        voice_prompt_hash: str,
        tts_model_name: str,
        output_dir: Path,
    ) -> SpeechResult:
        if not (text or "").strip():
            raise RuntimeError("TTS 텍스트가 비어 있습니다.")
        if not (voice_prompt_hash or "").strip():
            raise RuntimeError("voice_prompt_hash가 없습니다. /v1/voice/prepare 를 먼저 호출하세요.")

        output_dir.mkdir(parents=True, exist_ok=True)
        prepared = self._mm.get_prepared_voice(voice_prompt_hash)

        if CONFIG.mock_mode:
            audio_bytes = _silence_wav_bytes(1.0)
            h = hashlib.sha256(f"{voice_prompt_hash}::{text}".encode("utf-8", errors="ignore")).hexdigest()
            out_path = output_dir / f"{h}.wav"
            if not out_path.is_file():
                out_path.write_bytes(audio_bytes)
            return SpeechResult(audio_path=str(out_path), text=text)

        if prepared is None or prepared.voice_clone_prompt is None:
            raise RuntimeError(
                "voice clone prompt가 없습니다. 기준 음성을 다시 확정한 뒤 prepare를 호출하세요."
            )

        tts_model = self._ensure_tts_model(tts_model_name)
        # generate_voice_clone은 파일 경로가 아니라 (파형 리스트, sample_rate)를 돌려준다.
        generated = tts_model.generate_voice_clone(
            text=text,
            language=TTS_LANGUAGE,
            voice_clone_prompt=prepared.voice_clone_prompt,
            x_vector_only_mode=TTS_X_VECTOR_ONLY_MODE,
        )
        try:
            wavs, sample_rate = generated
            wav = wavs[0]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"TTS 생성 결과 형식을 알 수 없습니다: {type(generated)!r}"
            ) from exc

        h = hashlib.sha256(f"{voice_prompt_hash}::{text}".encode("utf-8", errors="ignore")).hexdigest()
        out_path = output_dir / f"{h}.wav"
        _write_wav(out_path, wav, sample_rate)
        return SpeechResult(audio_path=str(out_path), text=text)
