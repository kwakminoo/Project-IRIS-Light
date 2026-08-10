"""IRIS LearningEvent → ShowUI-Aloha Learner 입력 포맷."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from iris.learning.models import LearningEvent, SessionManifest
from iris.learning.privacy import redact_text_if_needed


def _aloha_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"


def _window_label(e: LearningEvent) -> str:
    proc = e.process_name or "unknown"
    title = e.window_title or ""
    if title and proc.lower() not in title.lower():
        return f"{proc} - {title}"
    return title or proc


def event_to_aloha_message(e: LearningEvent) -> str | None:
    if e.exclude_from_trace:
        return None
    et = e.event_type
    if et == "context" and e.metadata.get("kind") == "initial_window":
        return f"Initial Active Window: {_window_label(e)}"
    if et == "window_change":
        return f"Active Window: {_window_label(e)}"
    if et in {"click", "press"} and (e.metadata.get("button") or "left") == "left":
        if et == "press":
            return f"LClick at ({int(e.x or 0)}, {int(e.y or 0)})"
        return f"LClick at ({int(e.x or 0)}, {int(e.y or 0)})"
    if et == "release" and (e.metadata.get("button") or "left") == "left":
        return f"LRelease at ({int(e.x or 0)}, {int(e.y or 0)})"
    if et in {"right_click"} or (
        et in {"press", "release"} and e.metadata.get("button") == "right"
    ):
        kind = "RClick" if et != "release" else "RRelease"
        return f"{kind} at ({int(e.x or 0)}, {int(e.y or 0)})"
    if et == "double_click":
        return f"LDoubleClick at ({int(e.x or 0)}, {int(e.y or 0)})"
    if et == "drag":
        start = e.metadata.get("start") or (e.x, e.y)
        end = e.metadata.get("end") or (e.x, e.y)
        return (
            f"Drag from ({int(start[0])}, {int(start[1])}) "
            f"to ({int(end[0])}, {int(end[1])})"
        )
    if et == "scroll":
        dy = int(e.metadata.get("dy") or 0)
        direction = "up" if dy > 0 else "down"
        return f"Scroll {direction} at ({int(e.x or 0)}, {int(e.y or 0)})"
    if et == "key_down":
        key = e.key or ""
        if key == "[REDACTED]":
            return "Key Press: [REDACTED]"
        return f"Key Press: {key}"
    if et == "key_up":
        key = e.key or ""
        if key == "[REDACTED]":
            return "Key Release: [REDACTED]"
        return f"Key Release: {key}"
    if et == "type_text":
        text = redact_text_if_needed(
            e.text, window_title=e.window_title, process_name=e.process_name
        )
        return f"Type: {text}"
    return None


def write_aloha_input(
    session_path: Path,
    manifest: SessionManifest,
    events: list[LearningEvent],
) -> Path:
    """Aloha_Learn이 기대하는 inputs/ 로그(+메타) 작성. mp4는 recorder가 둠."""
    inputs = session_path / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    started = manifest.started_at or datetime.now().isoformat(timespec="seconds")
    # Aloha 헤더의 video_start_time 형식: "YYYY-MM-DD HH:MM:SS.mmm"
    try:
        dt = datetime.fromisoformat(started)
        video_start = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except ValueError:
        video_start = started.replace("T", " ")

    screen_info = {
        "0": {
            "x0": 0,
            "y0": 0,
            "width": manifest.screen_width or 1920,
            "height": manifest.screen_height or 1080,
            "scale_factor": manifest.scale_factor or 1.0,
        }
    }
    meta = {
        "video_start_time": video_start,
        "start_message": "IRIS learning recorder started",
        "recording_timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "screen_info": screen_info,
    }

    lines: list[str] = [
        "# Input Recording Log",
        f"# Started: {video_start}",
        f"# Metadata: {json.dumps(meta, ensure_ascii=False)}",
        "# Format: JSON per line",
        "# Fields: timestamp, message, window",
        "",
        json.dumps(
            {
                "timestamp": "00:00:00.000",
                "message": json.dumps(screen_info),
                "window": "System Info",
            },
            ensure_ascii=False,
        ),
    ]

    for e in events:
        msg = event_to_aloha_message(e)
        if not msg:
            continue
        lines.append(
            json.dumps(
                {
                    "timestamp": _aloha_ts(e.timestamp),
                    "message": msg,
                    "window": _window_label(e),
                },
                ensure_ascii=False,
            )
        )

    log_path = inputs / "recording.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest.aloha_log_path = str(log_path)

    # Aloha project layout 호환용 별칭
    (session_path / "aloha_input.log").write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
    return log_path
