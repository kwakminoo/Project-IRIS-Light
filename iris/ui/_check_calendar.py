"""ponytail: calendar storage / agent op / holiday cache self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.infrastructure.calendar_agent import (
    normalize_start_at,
    parse_calendar_ops,
    strip_calendar_ops,
)
from datetime import datetime, timedelta, timezone

from iris.storage.calendar_events import (
    add_event,
    delete_event,
    events_as_dicts,
    list_events,
    parse_event_instant,
    reminder_clock_now,
)
from iris.storage.database import Database
from iris.knowledge.iris_wiki import IrisWiki


def _assert_remind_compare_safe(start_iso: str) -> None:
    """2026-10-27 crash: naive now vs +09:00 start_at TypeError in the timer slot."""
    now = reminder_clock_now()
    start = parse_event_instant(start_iso)
    soon_until = now + timedelta(hours=24)
    _ = start < now
    _ = now <= start <= soon_until


def main() -> None:
    assert normalize_start_at("2026-08-04 15:30") == "2026-08-04T15:30:00"
    text = 'ok\n[[CALENDAR_OP]]{"op":"add","title":"회의","start_at":"2026-08-04T15:00:00"}[[/CALENDAR_OP]]'
    ops = parse_calendar_ops(text)
    assert ops and ops[0]["op"] == "add"
    assert "CALENDAR_OP" not in strip_calendar_ops(text)

    # Repro the 2026-10-27 launcher.log TypeError without MainWindow.
    _assert_remind_compare_safe("2026-11-04T10:30:00+09:00")
    _assert_remind_compare_safe("2026-08-04T10:00:00")
    past = (datetime.now(timezone.utc) - timedelta(days=2)).astimezone()
    assert parse_event_instant(past.isoformat()) < reminder_clock_now()

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        ev = add_event(db, title="테스트", start_at="2026-08-04T10:00:00", note="n", place="서울")
        assert ev.id > 0
        assert ev.place == "서울"
        assert len(list_events(db, year=2026, month=8)) == 1
        # Aware row like Hermes/chat calendar add (crash sample).
        db._execute(
            "INSERT INTO calendar_events "
            "(title, start_at, end_at, note, place, all_day, reminded_soon, "
            "reminded_overdue, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "aware crash sample",
                "2026-11-04T10:30:00+09:00",
                "2026-11-04T10:45:00+09:00",
                "",
                "",
                0,
                0,
                0,
                datetime.now().isoformat(),
            ),
        )
        db._commit()
        now = reminder_clock_now()
        for row in list_events(db):
            start = parse_event_instant(row.start_at)
            _ = start < now
        wiki = IrisWiki(user_root=Path(tmp) / "wiki")
        wiki.sync_schedule_markdown(events_as_dicts(list_events(db)))
        assert (wiki.user_root / "schedule" / "index.md").is_file()
        assert delete_event(db, ev.id)
        db._conn.close()
    print("calendar self-check ok")


if __name__ == "__main__":
    main()
