"""IDE 최근 열었던 폴더 — ~/.iris-light/ide-recent-folders.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from iris.system.hermes_iris_control_sync import iris_state_dir

_STORE_NAME = "ide-recent-folders.json"


def _store_path() -> Path:
    return iris_state_dir() / _STORE_NAME


def _load() -> list[dict[str, str]]:
    path = _store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _save(rows: list[dict[str, str]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_recent_folders(limit: int = 5) -> list[tuple[str, str]]:
    """(폴더명, 전체 경로) — 최근 순."""
    out: list[tuple[str, str]] = []
    for row in _load():
        path = str(row.get("path", "")).strip()
        if not path:
            continue
        name = str(row.get("name", "")).strip() or Path(path).name or path
        out.append((name, path))
        if len(out) >= limit:
            break
    return out


def record_opened_folder(path: Path) -> None:
    resolved = str(path.expanduser().resolve())
    name = path.name or resolved
    rows = [r for r in _load() if str(r.get("path", "")) != resolved]
    rows.insert(
        0,
        {
            "name": name,
            "path": resolved,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    _save(rows[:20])


def truncate_path_middle(path: str, max_len: int = 52) -> str:
    if len(path) <= max_len:
        return path
    head = max_len // 2 - 2
    tail = max_len - head - 3
    return f"{path[:head]}...{path[-tail:]}"


def next_iris_project_dir(parent: Path, *, base: str = "Iris Project") -> Path:
    """Create folder용 — 이름 입력 없이 쓸 고유 경로 (아직 만들지 않음)."""
    root = Path(parent).expanduser()
    candidate = root / base
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = root / f"{base} {n}"
        if not candidate.exists():
            return candidate
        n += 1


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        a = next_iris_project_dir(p)
        assert a.name == "Iris Project"
        a.mkdir()
        b = next_iris_project_dir(p)
        assert b.name == "Iris Project 2"
    print("ide_recent_folders ok")
