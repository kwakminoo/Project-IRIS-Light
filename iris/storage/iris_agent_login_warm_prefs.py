"""로그인 시 Iris Agent gateway 미리 기동 — user_preferences JSON.

키가 없으면 enabled=True (기존 사용자도 첫 Iris 열기·sync 후 워밍).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from iris.storage.database import Database

HERMES_LOGIN_WARM_KEY = "hermes_login_warm_v1"


@dataclass
class IrisAgentLoginWarmPrefs:
    enabled: bool = True


# Compat alias (Wave E).
HermesLoginWarmPrefs = IrisAgentLoginWarmPrefs


def load_hermes_login_warm(db: Database | None) -> IrisAgentLoginWarmPrefs:
    if db is None:
        return IrisAgentLoginWarmPrefs()
    raw = db.get_preference(HERMES_LOGIN_WARM_KEY, "")
    if not raw.strip():
        return IrisAgentLoginWarmPrefs()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return IrisAgentLoginWarmPrefs()
    if not isinstance(data, dict):
        return IrisAgentLoginWarmPrefs()
    if "enabled" not in data:
        return IrisAgentLoginWarmPrefs()
    return IrisAgentLoginWarmPrefs(enabled=bool(data.get("enabled")))


def save_hermes_login_warm(db: Database, prefs: IrisAgentLoginWarmPrefs) -> None:
    db.set_preference(
        HERMES_LOGIN_WARM_KEY,
        json.dumps({"enabled": bool(prefs.enabled)}),
    )


def _self_check() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        assert load_hermes_login_warm(db).enabled is True
        save_hermes_login_warm(db, IrisAgentLoginWarmPrefs(enabled=False))
        assert load_hermes_login_warm(db).enabled is False
        save_hermes_login_warm(db, IrisAgentLoginWarmPrefs(enabled=True))
        assert load_hermes_login_warm(db).enabled is True
        assert HermesLoginWarmPrefs is IrisAgentLoginWarmPrefs
        db.close()
    print("hermes_login_warm_prefs ok")


if __name__ == "__main__":
    _self_check()
