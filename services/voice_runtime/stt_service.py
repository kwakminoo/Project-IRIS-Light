from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CONFIG
from .model_manager import VoiceModelManager


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    language_probability: float


def _detect_compute_type() -> str:
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "float16"
    except Exception:
        pass
    return "int8"


class STTService:
    def __init__(self, model_manager: VoiceModelManager) -> None:
        self._mm = model_manager

    def _get_model_key(self, model_name: str, compute_type: str) -> str:
        return f"{model_name}:{compute_type}"

    def _load_model(self, model_name: str, compute_type: str) -> Any:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "faster-whisper가 설치되지 않았습니다. "
                "scripts/setup_voice_runtime 으로 .venv-voice를 구성하세요."
            ) from exc

        device = "cuda" if compute_type == "float16" else "cpu"
        try:
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(CONFIG.stt_models_dir),
            )
        except Exception as exc:  # noqa: BLE001
            if compute_type == "float16":
                # GPU 실패 → CPU int8 폴백
                return self._load_model(model_name, "int8")
            raise RuntimeError(f"STT 모델 로딩 실패 ({model_name}/{compute_type}): {exc}") from exc
        return model

    def _ensure_model(self, model_name: str, compute_type: str) -> Any:
        key = self._get_model_key(model_name, compute_type)
        existing = self._mm.get_stt(key)
        if existing is not None:
            return existing
        model = self._load_model(model_name, compute_type)
        # GPU 폴백으로 int8이 되었을 수 있어 실제 키도 함께 저장
        self._mm.set_stt(key, model)
        self._mm.set_stt(self._get_model_key(model_name, "int8"), model)
        return model

    def transcribe_b64(
        self,
        audio_b64: str,
        *,
        filename_hint: str = "audio.wav",
        model_name: str = "small",
        language: str = "ko",
        vad_filter: bool = True,
        beam_size: int = 5,
        condition_on_previous_text: bool = False,
        compute_type: str | None = None,
    ) -> TranscriptionResult:
        compute_type = compute_type or _detect_compute_type()
        wav_bytes = base64.b64decode(audio_b64)

        if CONFIG.mock_mode:
            return TranscriptionResult(
                text="[mock stt] (음성 인식 결과)",
                language="ko",
                language_probability=0.99,
            )

        model = self._ensure_model(model_name, compute_type)

        CONFIG.voice_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=Path(filename_hint).suffix or ".wav", delete=False
        ) as f:
            f.write(wav_bytes)
            temp_path = Path(f.name)

        lang_arg: str | None = None if (language or "").strip().lower() in ("", "auto") else language
        try:
            segments, info = model.transcribe(
                str(temp_path),
                language=lang_arg,
                vad_filter=vad_filter,
                beam_size=beam_size,
                condition_on_previous_text=condition_on_previous_text,
            )
            text = " ".join(s.text for s in segments).strip()
            language_out = getattr(info, "language", None) or (lang_arg or "ko")
            prob = float(getattr(info, "language_probability", 0.0) or 0.0)
            return TranscriptionResult(
                text=text or "",
                language=str(language_out),
                language_probability=prob,
            )
        finally:
            try:
                os.unlink(str(temp_path))
            except Exception:
                pass

    def transcribe_file(
        self,
        path: Path,
        *,
        model_name: str = "small",
        language: str = "ko",
    ) -> TranscriptionResult:
        audio_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return self.transcribe_b64(
            audio_b64,
            filename_hint=path.name,
            model_name=model_name,
            language=language,
        )
