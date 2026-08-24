"""음성 설정/선택값 — 기존 SQLite user_preferences 재사용."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from iris.storage.database import Database

VOICE_PREFS_KEY = "voice_prefs_v1"

_VOICE_DIR_NAME = "아이리스 녹음"
_LEGACY_VOICE_DIR_NAMES = ("1차 아이리스 녹음",)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_voice_data_dir() -> str:
    project = _project_root() / _VOICE_DIR_NAME
    if project.is_dir():
        return str(project)
    for name in _LEGACY_VOICE_DIR_NAMES:
        for candidate in (_project_root() / name, Path.home() / "Desktop" / name):
            if candidate.is_dir():
                return str(candidate)
    return str(project)


def resolve_saved_voice_data_dir(saved: str) -> str:
    raw = (saved or "").strip()
    if not raw:
        return default_voice_data_dir()
    path = Path(raw)
    if path.is_dir():
        return str(path)
    if path.name in _LEGACY_VOICE_DIR_NAMES:
        return default_voice_data_dir()
    return raw


@dataclass
class VoicePreferences:
    stt_enabled: bool = False
    stt_model: str = "small"
    stt_language: str = "ko"  # "ko" | "auto"
    stt_device_id: str = ""
    stt_speech_rms: float = 0.02  # 연속 청취 발화 임계 RMS
    stt_echo_tail_ms: int = 180
    voice_barge_in_enabled: bool = True
    voice_wake_word_enabled: bool = False
    voice_wake_words: str = "아이리스,Iris"
    voice_followup_window_sec: int = 20

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
    # 재생 단계에서만 적용하는 절제된 AI 비서 음향 효과. 원본 보이스 클론은 바꾸지 않는다.
    tts_ai_voice_fx_enabled: bool = True
    tts_ai_voice_fx_intensity: float = 0.75
    # qwen | qwen_custom | gpt_sovits
    tts_engine: str = "qwen"
    tts_custom_speaker: str = "iris"
    tts_custom_model_path: str = ""
    gpt_sovits_url: str = "http://127.0.0.1:9880"

    voice_runtime_url: str = "http://127.0.0.1:18765"
    voice_runtime_mock: bool = False
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
    try:
        prefs.stt_echo_tail_ms = max(0, int(data.get("stt_echo_tail_ms", prefs.stt_echo_tail_ms)))
    except (TypeError, ValueError):
        prefs.stt_echo_tail_ms = 180
    prefs.voice_barge_in_enabled = _to_bool(
        data.get("voice_barge_in_enabled"), prefs.voice_barge_in_enabled
    )
    prefs.voice_wake_word_enabled = _to_bool(
        data.get("voice_wake_word_enabled"), prefs.voice_wake_word_enabled
    )
    prefs.voice_wake_words = str(data.get("voice_wake_words", prefs.voice_wake_words) or "아이리스,Iris")
    try:
        prefs.voice_followup_window_sec = max(
            1,
            int(data.get("voice_followup_window_sec", prefs.voice_followup_window_sec)),
        )
    except (TypeError, ValueError):
        prefs.voice_followup_window_sec = 20
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
    prefs.tts_ai_voice_fx_enabled = _to_bool(
        data.get("tts_ai_voice_fx_enabled"), prefs.tts_ai_voice_fx_enabled
    )
    fx_intensity = _to_float(
        data.get("tts_ai_voice_fx_intensity"), prefs.tts_ai_voice_fx_intensity
    )
    if not math.isfinite(fx_intensity):
        fx_intensity = prefs.tts_ai_voice_fx_intensity
    prefs.tts_ai_voice_fx_intensity = max(0.0, min(1.0, fx_intensity))
    engine = str(data.get("tts_engine", prefs.tts_engine) or prefs.tts_engine).strip().lower()
    prefs.tts_engine = engine if engine in ("qwen", "qwen_custom", "gpt_sovits") else "qwen"
    prefs.tts_custom_speaker = str(data.get("tts_custom_speaker", prefs.tts_custom_speaker) or "iris")
    prefs.tts_custom_model_path = str(data.get("tts_custom_model_path", prefs.tts_custom_model_path) or "")
    prefs.gpt_sovits_url = str(data.get("gpt_sovits_url", prefs.gpt_sovits_url) or prefs.gpt_sovits_url)
    prefs.voice_runtime_url = str(data.get("voice_runtime_url", prefs.voice_runtime_url) or prefs.voice_runtime_url)
    # 구 기본 포트 8765는 다른 로컬 서비스와 충돌 → 새 기본으로 이전
    if prefs.voice_runtime_url.rstrip("/").endswith(":8765"):
        prefs.voice_runtime_url = "http://127.0.0.1:18765"
    prefs.voice_runtime_mock = _to_bool(data.get("voice_runtime_mock"), prefs.voice_runtime_mock)
    prefs.voice_data_dir = resolve_saved_voice_data_dir(
        str(data.get("voice_data_dir", prefs.voice_data_dir) or "")
    )
    prefs.pronunciation_dict_json = str(
        data.get("pronunciation_dict_json", prefs.pronunciation_dict_json) or ""
    )
    return prefs


def save_voice_preferences(db: Database, prefs: VoicePreferences) -> None:
    db.set_preference(
        VOICE_PREFS_KEY,
        json.dumps(asdict(prefs), ensure_ascii=False),
    )
