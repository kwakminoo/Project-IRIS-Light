"""사용자 프로필 — SQLite user_preferences에 JSON 저장."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from iris.storage.database import Database

PROFILE_PREF_KEY = "user_profile_v1"


@dataclass
class UserProfile:
    name: str = ""
    occupation: str = ""
    hobbies: str = ""
    interests: str = ""
    work_tasks: str = ""
    age: str = ""
    gender: str = ""
    residence: str = ""
    contact: str = ""
    email: str = ""


def load_user_profile(db: Database) -> UserProfile:
    raw = db.get_preference(PROFILE_PREF_KEY, "")
    if not raw.strip():
        return UserProfile()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return UserProfile()
        fields = UserProfile.__dataclass_fields__
        return UserProfile(**{k: str(data.get(k, "") or "") for k in fields})
    except (json.JSONDecodeError, TypeError):
        return UserProfile()


def save_user_profile(db: Database, profile: UserProfile) -> None:
    db.set_preference(
        PROFILE_PREF_KEY,
        json.dumps(asdict(profile), ensure_ascii=False),
    )
