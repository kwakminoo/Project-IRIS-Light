"""로컬 일정 — SQLite calendar_events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iris.storage.database import Database


@dataclass(frozen=True)
class CalendarEvent:
    id: int
    title: str
    start_at: str  # ISO local
    end_at: str
    note: str = ""
    place: str = ""
    all_day: bool = False
    reminded_soon: bool = False
    reminded_overdue: bool = False


def ensure_calendar_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            place TEXT NOT NULL DEFAULT '',
            all_day INTEGER NOT NULL DEFAULT 0,
            reminded_soon INTEGER NOT NULL DEFAULT 0,
            reminded_overdue INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    cols = {
        str(row["name"])
        for row in db._execute("PRAGMA table_info(calendar_events)").fetchall()
    }
    if "place" not in cols:
        db._execute(
            "ALTER TABLE calendar_events ADD COLUMN place TEXT NOT NULL DEFAULT ''"
        )
    db._commit()


def list_events(
    db: Database,
    *,
    year: int | None = None,
    month: int | None = None,
) -> list[CalendarEvent]:
    ensure_calendar_schema(db)
    rows = db._execute(
        "SELECT * FROM calendar_events ORDER BY start_at ASC, id ASC"
    ).fetchall()
    out: list[CalendarEvent] = []
    for row in rows:
        start = str(row["start_at"] or "")
        if year is not None:
            try:
                dt = datetime.fromisoformat(start)
            except ValueError:
                continue
            if dt.year != year:
                continue
            if month is not None and dt.month != month:
                continue
        out.append(
            CalendarEvent(
                id=int(row["id"]),
                title=str(row["title"] or ""),
                start_at=start,
                end_at=str(row["end_at"] or ""),
                note=str(row["note"] or ""),
                place=str(row["place"] or "") if "place" in row.keys() else "",
                all_day=bool(row["all_day"]),
                reminded_soon=bool(row["reminded_soon"]),
                reminded_overdue=bool(row["reminded_overdue"]),
            )
        )
    return out


def add_event(
    db: Database,
    *,
    title: str,
    start_at: str,
    end_at: str = "",
    note: str = "",
    place: str = "",
    all_day: bool = False,
) -> CalendarEvent:
    ensure_calendar_schema(db)
    title = (title or "").strip()
    if not title:
        raise ValueError("title required")
    start_at = (start_at or "").strip()
    if not start_at:
        raise ValueError("start_at required")
    place_s = (place or "").strip()
    note_s = (note or "").strip()
    end_s = (end_at or "").strip()
    cur = db._execute(
        """
        INSERT INTO calendar_events(
            title, start_at, end_at, note, place, all_day,
            reminded_soon, reminded_overdue, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
        """,
        (
            title,
            start_at,
            end_s,
            note_s,
            place_s,
            1 if all_day else 0,
            datetime.utcnow().isoformat(),
        ),
    )
    db._commit()
    eid = int(cur.lastrowid or 0)
    return CalendarEvent(
        id=eid,
        title=title,
        start_at=start_at,
        end_at=end_s,
        note=note_s,
        place=place_s,
        all_day=all_day,
    )


def delete_event(db: Database, event_id: int) -> bool:
    ensure_calendar_schema(db)
    cur = db._execute("DELETE FROM calendar_events WHERE id = ?", (int(event_id),))
    db._commit()
    return (cur.rowcount or 0) > 0


def mark_reminded(db: Database, event_id: int, *, soon: bool = False, overdue: bool = False) -> None:
    ensure_calendar_schema(db)
    if soon:
        db._execute(
            "UPDATE calendar_events SET reminded_soon = 1 WHERE id = ?",
            (int(event_id),),
        )
    if overdue:
        db._execute(
            "UPDATE calendar_events SET reminded_overdue = 1 WHERE id = ?",
            (int(event_id),),
        )
    db._commit()


def events_as_dicts(events: list[CalendarEvent]) -> list[dict[str, str]]:
    return [
        {
            "id": str(e.id),
            "title": e.title,
            "start_at": e.start_at,
            "end_at": e.end_at,
            "note": e.note,
            "place": e.place,
            "all_day": "1" if e.all_day else "0",
        }
        for e in events
    ]
