"""Hermes SOUL.md에 Iris 페르소나를 동기화.

Hermes는 HERMES_HOME/SOUL.md를 system prompt identity(slot #1)로 쓴다.
레포 `integrations/hermes-soul/SOUL.md`를 원본으로 두고, Iris↔Hermes sync 때 반영한다.
ponytail: 내용이 같으면 쓰기 생략. 덮어쓰기 전 SOUL.md.bak-iris 1회 백업.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from iris.system.hermes_iris_control_sync import hermes_home, project_root

_MARKER = "# IRIS Light Persona"


def repo_soul_path() -> Path:
    return project_root() / "integrations" / "hermes-soul" / "SOUL.md"


def hermes_soul_path() -> Path:
    return hermes_home() / "SOUL.md"


def load_iris_persona_text() -> str:
    """Ollama 직행 등 SOUL을 안 읽는 경로용. 없으면 빈 문자열."""
    path = repo_soul_path()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_soul() -> str:
    src = repo_soul_path()
    if not src.is_file():
        return "soul skip: repo SOUL.md missing"
    desired = src.read_text(encoding="utf-8", errors="replace")
    if _MARKER not in desired:
        return "soul skip: repo SOUL.md missing Iris marker"
    desired_norm = desired.strip() + "\n"

    dst = hermes_soul_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if dst.is_file():
        existing = dst.read_text(encoding="utf-8", errors="replace")
        if _sha(existing.strip() + "\n") == _sha(desired_norm):
            return "soul already current"

    bak = hermes_home() / "SOUL.md.bak-iris"
    if existing.strip() and not bak.is_file():
        bak.write_text(existing, encoding="utf-8")

    dst.write_text(desired_norm, encoding="utf-8")
    return "soul updated (Iris persona)"


if __name__ == "__main__":
    print(ensure_soul())
    text = load_iris_persona_text()
    assert _MARKER in text
    assert "아이리스" in text
    print("ok", len(text), "chars")
