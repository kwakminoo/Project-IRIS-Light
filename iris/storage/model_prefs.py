"""Ollama 선택 모델 영속화."""

from __future__ import annotations

from iris.storage.database import Database

SELECTED_MODEL_KEY = "ollama_selected_model_v1"


def load_selected_model(db: Database) -> str:
    return db.get_preference(SELECTED_MODEL_KEY, "").strip()


def save_selected_model(db: Database, runtime_name: str) -> None:
    name = (runtime_name or "").strip()
    if name:
        db.set_preference(SELECTED_MODEL_KEY, name)
