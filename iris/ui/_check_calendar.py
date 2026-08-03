"""ponytail: calendar storage / agent op / holiday cache self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.infrastructure.calendar_agent import (
    normalize_start_at,
    parse_calendar_ops,
    strip_calendar_ops,
)
from iris.storage.calendar_events import add_event, delete_event, list_events
from iris.storage.database import Database
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.calendar_events import events_as_dicts


def main() -> None:
    assert normalize_start_at("2026-08-04 15:30") == "2026-08-04T15:30:00"
    text = 'ok\n[[CALENDAR_OP]]{"op":"add","title":"회의","start_at":"2026-08-04T15:00:00"}[[/CALENDAR_OP]]'
    ops = parse_calendar_ops(text)
    assert ops and ops[0]["op"] == "add"
    assert "CALENDAR_OP" not in strip_calendar_ops(text)

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        ev = add_event(db, title="테스트", start_at="2026-08-04T10:00:00", note="n", place="서울")
        assert ev.id > 0
        assert ev.place == "서울"
        assert len(list_events(db, year=2026, month=8)) == 1
        wiki = IrisWiki(user_root=Path(tmp) / "wiki")
        wiki.sync_schedule_markdown(events_as_dicts(list_events(db)))
        assert (wiki.user_root / "schedule" / "index.md").is_file()
        assert delete_event(db, ev.id)
        db._conn.close()
    print("calendar self-check ok")


if __name__ == "__main__":
    main()
