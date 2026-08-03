---
name: iris-calendar
description: >
  Manage Iris Light calendar: open calendar workspace, list/add/delete schedules,
  select a day, change month, refresh KR public holidays.
  Use when: 일정 추가, 캘린더 열어, 내일 회의 잡아줘, 공휴일, 스케줄 삭제,
  open calendar, add event, list events, select day.
---

# Iris calendar

## Prefer Iris Control MCP

Use `iris_get_state` / `iris_get_catalog` / `iris_invoke` (server `iris-control`).
Do **not** invent local calendar files — schedules live in Iris DB + wiki `user/schedule/`.

## Steps

1. `iris_get_state` — note `workspace_mode`.
2. Open calendar if needed:
   `iris_invoke` → `workspace.open_calendar`
3. Inspect:
   - `calendar.status` — selected day + events
   - `calendar.list_events` — full list
4. Navigate:
   - `calendar.set_month` args `{year, month}`
   - `calendar.select_day` args `{date: "YYYY-MM-DD"}`
5. Add schedule:
   `calendar.add_event` args
   `{title, start_at: "YYYY-MM-DDTHH:MM:SS", note?, place?, end_at?}`
6. Delete:
   `calendar.delete_event` args `{id}`
7. Holidays (needs `.env` `IRIS_DATA_GO_KR_SERVICE_KEY`):
   `calendar.refresh_holidays`

## Notes

- After add/delete, Iris syncs wiki `schedule/index.md`.
- Upcoming/overdue events raise Iris notifications automatically.
- Confirm with `calendar.status` after mutations.
