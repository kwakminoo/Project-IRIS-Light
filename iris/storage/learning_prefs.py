"""업무 학습 / VLM / 권한 설정 — user_preferences JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from iris.storage.database import Database

LEARNING_PREFS_KEY = "learning_prefs_v1"

# low | normal | high | unrestricted
PERMISSION_LEVELS = ("low", "normal", "high", "unrestricted")


@dataclass
class LearningPreferences:
    permission_level: str = "normal"
    # ollama | openai | anthropic | auto
    vlm_provider: str = "auto"
    vlm_model: str = ""  # ollama runtime name or API model id
    api_fallback_provider: str = ""  # openai | anthropic
    api_fallback_model: str = ""
    aloha_runtime_python: str = ""  # override path; empty → default runtime
    skip_vlm_guide_once: bool = False


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def load_learning_preferences(db: Database | None) -> LearningPreferences:
    if db is None:
        return LearningPreferences()
    raw = db.get_preference(LEARNING_PREFS_KEY, "")
    if not raw.strip():
        return LearningPreferences()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return LearningPreferences()
    if not isinstance(data, dict):
        return LearningPreferences()
    prefs = LearningPreferences()
    level = str(data.get("permission_level") or prefs.permission_level).strip().lower()
    prefs.permission_level = level if level in PERMISSION_LEVELS else "normal"
    prefs.vlm_provider = str(data.get("vlm_provider") or prefs.vlm_provider).strip() or "auto"
    prefs.vlm_model = str(data.get("vlm_model") or "").strip()
    prefs.api_fallback_provider = str(data.get("api_fallback_provider") or "").strip()
    prefs.api_fallback_model = str(data.get("api_fallback_model") or "").strip()
    prefs.aloha_runtime_python = str(data.get("aloha_runtime_python") or "").strip()
    prefs.skip_vlm_guide_once = _to_bool(data.get("skip_vlm_guide_once"), False)
    return prefs


def save_learning_preferences(db: Database, prefs: LearningPreferences) -> None:
    db.set_preference(LEARNING_PREFS_KEY, json.dumps(asdict(prefs), ensure_ascii=False))
