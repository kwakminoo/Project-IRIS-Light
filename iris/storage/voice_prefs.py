"""음성 설정/선택값 — 기존 SQLite user_preferences 재사용."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from iris.storage.database import Database

VOICE_PREFS_KEY = "voice_prefs_v1"

# 사용자 지정 기본 경로. 없으면 프로젝트 내 동명 폴더를 쓴다.
_DESKTOP_VOICE_DIR = Path(r"c:\Users\kwakm\Desktop\1차 아이리스 녹음")
_PROJECT_VOICE_DIR = Path(__file__).resolve().parents[2] / "1차 아이리스 녹음"


def default_voice_data_dir() -> str:
    if _DESKTOP_VOICE_DIR.is_dir():
        return str(_DESKTOP_VOICE_DIR)
    if _PROJECT_VOICE_DIR.is_dir():
        return str(_PROJECT_VOICE_DIR)
    return str(_DESKTOP_VOICE_DIR)


@dataclass
class VoicePreferences:
    stt_enabled: bool = False
    stt_model: str = "small"
    stt_language: str = "ko"  # "ko" | "auto"
    stt_device_id: str = ""
    stt_speech_rms: float = 0.02  # 연속 청취 발화 임계 RMS

    tts_enabled: bool = False
    tts_mode: str = "off"  # off | manual | auto
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    tts_reference_audio: str = ""
    tts_reference_text: str = ""
    tts_voice_prompt_hash: str = ""
    tts_volume: float = 1.0
    # 저장소에 커밋된 IRIS 보이스 프로필을 쓴다. 끄면 아래 기준 음성 파일로 돌아간다.
    tts_use_voice_profile: bool = True
    # 문장 유형에 맞춰 톤을 자동 선택. 끄면 항상 기본(neutral) 톤.
    tts_tone_routing: bool = True

    voice_runtime_url: str = "http://127.0.0.1:18765"
    voice_runtime_mock: bool = True
    voice_data_dir: str = ""
    pronunciation_dict_json: str = ""

    def __post_init__(self) -> None:
        if not (self.voice_data_dir or "").strip():
            self.voice_data_dir = default_voice_data_dir()


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_voice_preferences(db: Database) -> VoicePreferences:
    raw = db.get_preference(VOICE_PREFS_KEY, "")
    if not raw.strip():
        return VoicePreferences()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return VoicePreferences()
    if not isinstance(data, dict):
        return VoicePreferences()

    prefs = VoicePreferences()
    prefs.stt_enabled = _to_bool(data.get("stt_enabled"), prefs.stt_enabled)
    prefs.stt_model = str(data.get("stt_model", prefs.stt_model) or prefs.stt_model)
    prefs.stt_language = str(data.get("stt_language", prefs.stt_language) or prefs.stt_language)
    prefs.stt_device_id = str(data.get("stt_device_id", prefs.stt_device_id) or "")
    prefs.stt_speech_rms = _to_float(data.get("stt_speech_rms"), prefs.stt_speech_rms)
    if prefs.stt_speech_rms <= 0:
        prefs.stt_speech_rms = 0.02
    prefs.tts_enabled = _to_bool(data.get("tts_enabled"), prefs.tts_enabled)
    prefs.tts_mode = str(data.get("tts_mode", prefs.tts_mode) or prefs.tts_mode)
    prefs.tts_model = str(data.get("tts_model", prefs.tts_model) or prefs.tts_model)
    prefs.tts_reference_audio = str(data.get("tts_reference_audio", prefs.tts_reference_audio) or "")
    prefs.tts_reference_text = str(data.get("tts_reference_text", prefs.tts_reference_text) or "")
    prefs.tts_voice_prompt_hash = str(data.get("tts_voice_prompt_hash", prefs.tts_voice_prompt_hash) or "")
    prefs.tts_volume = _to_float(data.get("tts_volume"), prefs.tts_volume)
    prefs.tts_use_voice_profile = _to_bool(
        data.get("tts_use_voice_profile"), prefs.tts_use_voice_profile
    )
    prefs.tts_tone_routing = _to_bool(data.get("tts_tone_routing"), prefs.tts_tone_routing)
    prefs.voice_runtime_url = str(data.get("voice_runtime_url", prefs.voice_runtime_url) or prefs.voice_runtime_url)
    # 구 기본 포트 8765는 다른 로컬 서비스와 충돌 → 새 기본으로 이전
    if prefs.voice_runtime_url.rstrip("/").endswith(":8765"):
        prefs.voice_runtime_url = "http://127.0.0.1:18765"
    prefs.voice_runtime_mock = _to_bool(data.get("voice_runtime_mock"), prefs.voice_runtime_mock)
    prefs.voice_data_dir = str(data.get("voice_data_dir", prefs.voice_data_dir) or "") or default_voice_data_dir()
    prefs.pronunciation_dict_json = str(
        data.get("pronunciation_dict_json", prefs.pronunciation_dict_json) or ""
    )
    return prefs


def save_voice_preferences(db: Database, prefs: VoicePreferences) -> None:
    db.set_preference(
        VOICE_PREFS_KEY,
        json.dumps(asdict(prefs), ensure_ascii=False),
    )
