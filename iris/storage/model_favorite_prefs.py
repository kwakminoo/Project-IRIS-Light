"""Persist model picker favorites by runtime id."""

from __future__ import annotations

import json

from iris.storage.database import Database

FAVORITES_KEY = "model_favorites_v1"


def load_model_favorites(db: Database | None) -> list[str]:
    if db is None:
        return []
    try:
        values = json.loads(db.get_preference(FAVORITES_KEY, ""))
    except (TypeError, ValueError):
        return []
    if not isinstance(values, dict) or not isinstance(values.get("runtimes"), list):
        return []
    return list(dict.fromkeys(
        value.strip() for value in values["runtimes"]
        if isinstance(value, str) and value.strip()
    ))


def toggle_model_favorite(db: Database, runtime: str) -> bool:
    key = (runtime or "").strip()
    if not key:
        return False
    current = load_model_favorites(db)
    added = key not in current
    values = [value for value in current if value != key]
    if added:
        values.append(key)
    db.set_preference(FAVORITES_KEY, json.dumps({"runtimes": values}))
    return added
