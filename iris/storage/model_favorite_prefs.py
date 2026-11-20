"""AI 모델 즐겨찾기 — user_preferences JSON (`model_favorites_v1`)."""

from __future__ import annotations

import json
from collections.abc import Iterable

from iris.storage.database import Database

FAVORITES_KEY = "model_favorites_v1"


def _normalize_runtimes(runtimes: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in runtimes:
        s = (raw or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def load_model_favorites(db: Database | None) -> list[str]:
    if db is None:
        return []
    raw = db.get_preference(FAVORITES_KEY, "")
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    runtimes = data.get("runtimes")
    if not isinstance(runtimes, list):
        return []
    return _normalize_runtimes(x for x in runtimes if isinstance(x, str))


def save_model_favorites(db: Database, runtimes: list[str] | Iterable[str]) -> None:
    cleaned = _normalize_runtimes(runtimes)
    db.set_preference(FAVORITES_KEY, json.dumps({"runtimes": cleaned}))


def is_model_favorite(
    runtimes: list[str] | set[str] | frozenset[str],
    runtime: str,
) -> bool:
    key = (runtime or "").strip()
    if not key:
        return False
    return key in runtimes


def toggle_model_favorite(db: Database, runtime: str) -> bool:
    key = (runtime or "").strip()
    if not key:
        return False
    current = load_model_favorites(db)
    if key in current:
        save_model_favorites(db, [r for r in current if r != key])
        return False
    current.append(key)
    save_model_favorites(db, current)
    return True


def _self_check() -> None:
    import tempfile
    from pathlib import Path

    assert is_model_favorite([], "a") is False
    assert is_model_favorite(["a", "b"], "a") is True
    assert is_model_favorite({"a"}, "a") is True
    assert is_model_favorite(["a"], "") is False
    assert is_model_favorite(["a"], "  ") is False

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        assert load_model_favorites(None) == []
        assert load_model_favorites(db) == []
        assert toggle_model_favorite(db, "") is False
        assert load_model_favorites(db) == []

        assert toggle_model_favorite(db, "api:nv:foo") is True
        assert load_model_favorites(db) == ["api:nv:foo"]
        assert toggle_model_favorite(db, "llama3.2:latest") is True
        assert load_model_favorites(db) == ["api:nv:foo", "llama3.2:latest"]
        assert toggle_model_favorite(db, "api:nv:foo") is False
        assert load_model_favorites(db) == ["llama3.2:latest"]

        save_model_favorites(db, ["  x  ", "", "y", "x", "  y "])
        assert load_model_favorites(db) == ["x", "y"]

        db.set_preference(FAVORITES_KEY, "not-json")
        assert load_model_favorites(db) == []
        db.set_preference(FAVORITES_KEY, json.dumps(["oops"]))
        assert load_model_favorites(db) == []
        db.set_preference(FAVORITES_KEY, json.dumps({"runtimes": "nope"}))
        assert load_model_favorites(db) == []
        db.close()
    print("model_favorite_prefs ok")


if __name__ == "__main__":
    _self_check()
