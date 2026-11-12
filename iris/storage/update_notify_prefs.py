"""아이리스·아이리스 에이전트 업데이트 알림 허용 — user_preferences JSON.

기본은 둘 다 끔. 켠 채팅에서만 시작·새 채팅마다 한 번 안내한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from iris.storage.database import Database

UPDATE_NOTIFY_KEY = "update_notify_v1"


@dataclass
class UpdateNotifyPrefs:
    iris: bool = False
    agent: bool = False

    @property
    def hermes(self) -> bool:
        """Read-compat for pre-Wave-E callers."""
        return self.agent


def should_show_update_prompt(*, allowed: bool, same_chat: bool, available: bool) -> bool:
    """허용되고, 이번 확인이 지금 채팅 것이고, 업데이트가 있을 때만."""
    return bool(allowed) and bool(same_chat) and bool(available)


def load_update_notify(db: Database | None) -> UpdateNotifyPrefs:
    if db is None:
        return UpdateNotifyPrefs()
    raw = db.get_preference(UPDATE_NOTIFY_KEY, "")
    if not raw.strip():
        return UpdateNotifyPrefs()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return UpdateNotifyPrefs()
    if not isinstance(data, dict):
        return UpdateNotifyPrefs()
    if "agent" in data:
        agent = bool(data.get("agent"))
    else:
        agent = bool(data.get("hermes"))
    return UpdateNotifyPrefs(
        iris=bool(data.get("iris")),
        agent=agent,
    )


def save_update_notify(db: Database, prefs: UpdateNotifyPrefs) -> None:
    db.set_preference(
        UPDATE_NOTIFY_KEY,
        json.dumps({"iris": bool(prefs.iris), "agent": bool(prefs.agent)}),
    )


def _self_check() -> None:
    import tempfile
    from pathlib import Path

    assert should_show_update_prompt(allowed=False, same_chat=True, available=True) is False
    assert should_show_update_prompt(allowed=True, same_chat=False, available=True) is False
    assert should_show_update_prompt(allowed=True, same_chat=True, available=False) is False
    assert should_show_update_prompt(allowed=True, same_chat=True, available=True) is True
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        assert load_update_notify(db) == UpdateNotifyPrefs()
        save_update_notify(db, UpdateNotifyPrefs(iris=True, agent=False))
        got = load_update_notify(db)
        assert got.iris is True and got.agent is False and got.hermes is False
        # legacy JSON key "hermes" still loads
        db.set_preference(UPDATE_NOTIFY_KEY, json.dumps({"iris": False, "hermes": True}))
        legacy = load_update_notify(db)
        assert legacy.agent is True and legacy.hermes is True
        db.close()
    print("update_notify_prefs ok")


if __name__ == "__main__":
    _self_check()
