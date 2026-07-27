"""사용자 프로필 — SQLite user_preferences에 JSON 저장."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from iris.storage.database import Database

PROFILE_PREF_KEY = "user_profile_v1"

_STR_FIELDS = (
    "name",
    "occupation",
    "hobbies",
    "interests",
    "work_tasks",
    "age",
    "gender",
    "residence",
    "contact",
    "email",
    "preferred_ide",
    "ide_exe_path",
    "ide_cli_path",
    "project_root",
)


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
    # IDE Companion — preferred_ide: catalog id | "custom"
    preferred_ide: str = "cursor"
    ide_exe_path: str = ""
    ide_cli_path: str = ""
    project_root: str = ""
    # 프로젝트 유사검색 부모 폴더들 (비우면 project_ops 기본 후보 사용)
    project_parents: list[str] = field(default_factory=list)


def parse_project_parents(raw: object) -> list[str]:
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            raw = json.loads(s)
        except json.JSONDecodeError:
            return [s] if s else []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        p = str(item or "").strip()
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def load_user_profile(db: Database) -> UserProfile:
    raw = db.get_preference(PROFILE_PREF_KEY, "")
    if not raw.strip():
        return UserProfile()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return UserProfile()
        kwargs = {k: str(data.get(k, "") or "") for k in _STR_FIELDS}
        kwargs["project_parents"] = parse_project_parents(data.get("project_parents"))
        return UserProfile(**kwargs)
    except (json.JSONDecodeError, TypeError):
        return UserProfile()


def save_user_profile(db: Database, profile: UserProfile) -> None:
    payload = asdict(profile)
    payload["project_parents"] = parse_project_parents(payload.get("project_parents"))
    db.set_preference(
        PROFILE_PREF_KEY,
        json.dumps(payload, ensure_ascii=False),
    )
