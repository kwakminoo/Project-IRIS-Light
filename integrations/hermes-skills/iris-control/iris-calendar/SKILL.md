---
name: iris-calendar
description: >
  Manage Iris Light calendar: open calendar workspace, list/add/delete schedules,
  select a day, change month, refresh KR public holidays.
  Use when: 일정 추가, 캘린더 열어, 내일 회의 잡아줘, 공휴일, 스케줄 삭제,
  open calendar, add event, list events, select day.
---

# Iris calendar

## Prefer native seed tools

- List schedules: `calendar_list_events`.
- Live UI mode: `get_state` when needed.
- Open/add/delete/select still use Control actions via the product tool path —
  do **not** invent local calendar files; schedules live in Iris DB + wiki `user/schedule/`.
  Action IDs below use dots; callable function names replace dots with underscores.

## Steps

1. `get_state` — note `workspace_mode` (needs Iris UI; if `requires_iris_ui`, ask user to speak in Iris chat or click).
2. Open calendar if needed:
   `workspace_open_calendar` with `{}`
3. Inspect:
   - `calendar.status` — selected day + events
   - `calendar_list_events` — full list (native)
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
