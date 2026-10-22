"""위키 페이지별 개인 메모 — vault 밖 ~/.iris-light 저장."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from iris.system.hermes_iris_control_sync import iris_state_dir

_STORE_NAME = "wiki-page-memos.json"


@dataclass(frozen=True)
class PageMemo:
    memo_id: str
    note_rel: str
    body: str
    created_at: str
    updated_at: str


def _store_path(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else iris_state_dir()
    return base / _STORE_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[dict]] = {}
    for key, rows in data.items():
        if not isinstance(key, str) or not isinstance(rows, list):
            continue
        out[key] = [r for r in rows if isinstance(r, dict)]
    return out


def _save(path: Path, data: dict[str, list[dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _row_to_memo(row: dict) -> PageMemo | None:
    memo_id = str(row.get("memo_id", "")).strip()
    note_rel = str(row.get("note_rel", "")).strip()
    body = str(row.get("body", ""))
    if not memo_id or not note_rel:
        return None
    return PageMemo(
        memo_id=memo_id,
        note_rel=note_rel,
        body=body,
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


class PageMemoStore:
    """note_rel 단위 CRUD. vault/위키 폴더에 파일을 만들지 않는다."""

    def __init__(self, root: Path | None = None) -> None:
        self._path = _store_path(root)

    def list(self, note_rel: str) -> list[PageMemo]:
        key = (note_rel or "").strip()
        if not key:
            return []
        rows = _load(self._path).get(key, [])
        out: list[PageMemo] = []
        for row in rows:
            memo = _row_to_memo({**row, "note_rel": key})
            if memo is not None:
                out.append(memo)
        return out

    def add(self, note_rel: str, body: str) -> PageMemo:
        key = (note_rel or "").strip()
        if not key:
            raise ValueError("note_rel required")
        text = (body or "").strip()
        if not text:
            raise ValueError("body required")
        stamp = _now()
        memo = PageMemo(
            memo_id=uuid.uuid4().hex,
            note_rel=key,
            body=text,
            created_at=stamp,
            updated_at=stamp,
        )
        data = _load(self._path)
        rows = list(data.get(key, []))
        rows.append(asdict(memo))
        data[key] = rows
        _save(self._path, data)
        return memo

    def update(self, note_rel: str, memo_id: str, body: str) -> PageMemo | None:
        key = (note_rel or "").strip()
        mid = (memo_id or "").strip()
        text = (body or "").strip()
        if not key or not mid or not text:
            return None
        data = _load(self._path)
        rows = list(data.get(key, []))
        for i, row in enumerate(rows):
            if str(row.get("memo_id", "")).strip() != mid:
                continue
            stamp = _now()
            updated = {
                **row,
                "note_rel": key,
                "memo_id": mid,
                "body": text,
                "updated_at": stamp,
                "created_at": str(row.get("created_at") or stamp),
            }
            rows[i] = updated
            data[key] = rows
            _save(self._path, data)
            return _row_to_memo(updated)
        return None

    def delete(self, note_rel: str, memo_id: str) -> bool:
        key = (note_rel or "").strip()
        mid = (memo_id or "").strip()
        if not key or not mid:
            return False
        data = _load(self._path)
        rows = list(data.get(key, []))
        kept = [r for r in rows if str(r.get("memo_id", "")).strip() != mid]
        if len(kept) == len(rows):
            return False
        if kept:
            data[key] = kept
        else:
            data.pop(key, None)
        _save(self._path, data)
        return True

    def count(self, note_rel: str) -> int:
        return len(self.list(note_rel))
