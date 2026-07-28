from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VoiceRuntimeConfig:
    api_host: str = "127.0.0.1"
    # ponytail: 8765는 다른 로컬 서비스와 충돌한 적 있음 → voice 전용 포트
    api_port: int = 18765

    iris_home_dir: Path = Path.home() / ".iris-light"
    voice_dir: Path = iris_home_dir / "voice"
    models_dir: Path = iris_home_dir / "models"
    stt_models_dir: Path = models_dir / "stt"
    tts_models_dir: Path = models_dir / "tts"

    voice_manifest_jsonl: Path = voice_dir / "manifest.jsonl"
    voice_manifest_csv: Path = voice_dir / "manifest.csv"
    voice_selection_path: Path = voice_dir / "selection.json"

    # 앱/테스트에서 실제 모델 다운로드를 피하기 위한 기본값.
    mock_mode: bool = os.environ.get("VOICE_RUNTIME_MOCK", "1").strip() in ("1", "true", "True")


CONFIG = VoiceRuntimeConfig()

