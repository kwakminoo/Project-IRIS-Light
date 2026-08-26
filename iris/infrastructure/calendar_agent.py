"""캘린더 아이리스 컨텍스트 / 응답 내 일정 연산 파싱."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from iris.storage.calendar_events import CalendarEvent

_OP_RE = re.compile(
    r"\[\[CALENDAR_OP\]\]\s*(\{.*?\})\s*\[\[/CALENDAR_OP\]\]",
    re.DOTALL | re.IGNORECASE,
)


def build_calendar_agent_context(
    *,
    events: list[CalendarEvent],
    selected_day: str,
    holidays: list[str],
) -> str:
    lines = [
        "당신은 Iris Light 캘린더 도우미입니다. 기본 페르소나(SOUL)의 말투·판단 원칙을 따릅니다.",
        "일정 추가·조회·삭제는 가능하면 Iris Control MCP(`iris_invoke`)를 사용하세요:",
        "- workspace.open_calendar",
        "- calendar.add_event {title, start_at, note?, place?}",
        "- calendar.list_events / calendar.status",
        "- calendar.select_day {date}",
        "- calendar.delete_event {id}",
        "- calendar.set_month {year, month}",
        "- calendar.refresh_holidays",
        "- 기본 화면/홈: workspace.open_assistant",
        "- 마이크: voice.mic_off / voice.mic_on",
        "MCP를 쓸 수 없을 때만 아래 블록을 응답 끝에 포함하세요.",
        "일반 설명은 한국어로 짧게, 마크다운 가능.",
        "",
        "형식:",
        '[[CALENDAR_OP]]{"op":"add","title":"회의","start_at":"2026-08-04T15:00:00","place":"","note":""}[[/CALENDAR_OP]]',
        '[[CALENDAR_OP]]{"op":"delete","id":12}[[/CALENDAR_OP]]',
        '[[CALENDAR_OP]]{"op":"list"}[[/CALENDAR_OP]]',
        "",
        f"오늘: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"선택된 날짜: {selected_day}",
    ]
    if holidays:
        lines.append("선택일 공휴일: " + ", ".join(holidays))
    lines.append("")
    lines.append("등록된 일정:")
    if not events:
        lines.append("- (없음)")
    else:
        for ev in events[:40]:
            lines.append(f"- id={ev.id} {ev.start_at} {ev.title}")
    return "\n".join(lines)


def strip_calendar_ops(text: str) -> str:
    return _OP_RE.sub("", text or "").strip()


def parse_calendar_ops(text: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for match in _OP_RE.finditer(text or ""):
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("op"):
            ops.append(data)
    return ops


def normalize_start_at(value: str) -> str:
    """'YYYY-MM-DD HH:MM' / ISO → ISO."""
    s = (value or "").strip().replace("/", "-")
    if not s:
        raise ValueError("empty start")
    if "T" not in s and " " in s:
        s = s.replace(" ", "T", 1)
    if len(s) == 10:
        s = f"{s}T09:00:00"
    # allow HH:MM without seconds
    try:
        datetime.fromisoformat(s)
        if len(s) == 16:
            s = f"{s}:00"
        return s
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            continue
    raise ValueError(f"bad datetime: {value}")
