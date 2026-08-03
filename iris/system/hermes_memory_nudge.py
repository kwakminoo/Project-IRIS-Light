"""Ensure Hermes MEMORY mentions Iris Control tools (optional nudge)."""

from __future__ import annotations

import re

from iris.system.hermes_iris_control_sync import hermes_home

_MARKER = "<!-- iris-control-nudge-v6 -->"
_BLOCK = """<!-- iris-control-nudge-v6 -->
## Iris Light UI control
When the user asks to open IDE / start coding / Companion / "ide 켜줘" / open a project / 아이리스 라이트 작업 시작:
1. Prefer MCP tools `iris_get_state`, `iris_get_catalog`, `iris_invoke` (skills: iris-work-start, iris-work-end, iris-session-status, iris-vibe-code, iris-calendar).
2. "ide 켜줘" / open IDE only: `iris_invoke` → `ide.enter_companion`.
3. Do NOT use terminal `cursor`/`code` alone — that skips Iris Companion tiling.
4. Do NOT claim Iris has no IDE GUI — Iris launches the preferred IDE via control surface.
5. Do NOT treat Hermes terminal cwd as Iris project_root.
6. Named project (e.g. AI guitar tab): `iris_invoke` → `project.open_similar` with `args.query`.
7. Absolute path: `iris_invoke` → `ide.open_folder` with `args.path`.
8. "아이리스 라이트 작업" with no other project name: `project.open_similar` query `iris light`.
9. If open_similar returns ambiguous/low_score: show `matches`, ask user, then `ide.open_folder`.
10. Parents for search come from Iris settings (`project_parents`); inspect via `project.list_parents`.
11. After creating/writing code: `project.write_file` with `open=true` (default typewriter: empty tab → wait visible → type into editor). Use `typewriter:false` only for instant dump.
12. On run requests: `project.run` — output in **IDE integrated terminal** (not a log file tab); only summarize in chat.
13. Calendar / 일정: `workspace.open_calendar`, then `calendar.add_event` / `calendar.list_events` / `calendar.select_day` / `calendar.delete_event` (skill iris-calendar).
"""


def _strip_old_nudge(text: str) -> str:
    # ponytail: HTML 주석 마커부터 다음 다른 HTML 주석 또는 EOF까지 제거
    return re.sub(
        r"<!--\s*iris-control-nudge(?:-v\d+)?\s*-->[\s\S]*?(?=\n<!--|\Z)",
        "",
        text,
    ).rstrip() + ("\n" if text.strip() else "")


def ensure_memory_nudge() -> str:
    mem_dir = hermes_home() / "memories"
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = mem_dir / "MEMORY.md"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if (
        _MARKER in existing
        and "typewriter" in existing
        and "integrated terminal" in existing
        and "iris-vibe-code" in existing
        and "iris-calendar" in existing
    ):
        return "memory nudge already present"
    cleaned = _strip_old_nudge(existing) if "iris-control-nudge" in existing else existing
    text = cleaned.rstrip() + ("\n\n" if cleaned.strip() else "") + _BLOCK.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    return "memory nudge updated (v6)"


if __name__ == "__main__":
    print(ensure_memory_nudge())
