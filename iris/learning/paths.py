"""학습 세션 파일 경로 — SQLite에는 path만 저장."""

from __future__ import annotations

from pathlib import Path


def learning_root() -> Path:
    root = Path.home() / ".iris-light" / "learning"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_dir(session_id: str) -> Path:
    d = learning_root() / "sessions" / session_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "inputs").mkdir(exist_ok=True)
    (d / "screenshots").mkdir(exist_ok=True)
    (d / "processed").mkdir(exist_ok=True)
    return d


def traces_dir() -> Path:
    d = learning_root() / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def aloha_vendor_root() -> Path:
    return Path(__file__).resolve().parents[2] / "integrations" / "showui-aloha"


def aloha_learn_root() -> Path:
    return aloha_vendor_root() / "Aloha_Learn"


def aloha_act_root() -> Path:
    return aloha_vendor_root() / "Aloha_Act"
