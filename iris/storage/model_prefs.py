"""Ollama 선택 모델·모델 정리 결과 영속화."""

from __future__ import annotations

import json

from iris.storage.database import Database

SELECTED_MODEL_KEY = "ollama_selected_model_v1"
OLLAMA_PROBE_KEY = "ollama_model_probe_v1"


def load_selected_model(db: Database) -> str:
    return db.get_preference(SELECTED_MODEL_KEY, "").strip()


def save_selected_model(db: Database, runtime_name: str) -> None:
    name = (runtime_name or "").strip()
    if name:
        db.set_preference(SELECTED_MODEL_KEY, name)


def pick_reload_model(saved: str, current: str = "", settings: str = "") -> str:
    """Ollama 껐다 켜도 마지막 사용자 선택을 유지."""
    return (saved or current or settings or "").strip()


def load_ollama_model_probes(db: Database) -> dict[str, dict[str, str]]:
    raw = db.get_preference(OLLAMA_PROBE_KEY, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, val in data.items():
        name = str(key).strip()
        if not name or not isinstance(val, dict):
            continue
        out[name] = {
            "state": str(val.get("state") or ""),
            "tool": str(val.get("tool") or ""),
        }
    return out


def save_ollama_model_probe(
    db: Database, model: str, *, state: str, tool: str
) -> None:
    name = (model or "").strip()
    if not name:
        return
    probes = load_ollama_model_probes(db)
    probes[name] = {"state": state, "tool": tool}
    db.set_preference(OLLAMA_PROBE_KEY, json.dumps(probes, ensure_ascii=False))


def ollama_cleanup_has_verdict(db: Database) -> bool:
    """한 번이라도 사용가능/제외가 확정됐으면 True. 전부 미확정이면 다음 기동에 다시 정리."""
    return any(
        rec.get("state") in ("ok", "unavailable")
        for rec in load_ollama_model_probes(db).values()
    )


if __name__ == "__main__":
    assert pick_reload_model("gemma4:e2b", "api:oa:gpt", "other") == "gemma4:e2b"
    assert pick_reload_model("", "api:oa:gpt", "other") == "api:oa:gpt"
    assert pick_reload_model("", "", "other") == "other"
    print("model_prefs ok")
