"""Ensure Hermes MEMORY mentions Iris Control tools (optional nudge)."""

from __future__ import annotations

import re

from iris.system.hermes_iris_control_sync import hermes_home

_MARKER = "<!-- iris-control-nudge-v10 -->"
_BLOCK = """<!-- iris-control-nudge-v10 -->
## Iris Light UI control
When the user asks to open IDE / start coding / Companion / "ide 켜줘" / open a project / 아이리스 라이트 작업 시작:
1. Prefer MCP tools `iris_get_state`, `iris_get_catalog`, `iris_invoke` (skills: iris-work-start, iris-work-end, iris-session-status, iris-vibe-code, iris-calendar, iris-wiki, iris-email).
2. "ide 켜줘" / open IDE only: `iris_invoke` → `ide.enter_companion`.
3. Do NOT use terminal `cursor`/`code` alone — that skips Iris Companion tiling.
4. Do NOT claim Iris has no IDE GUI — Iris launches the preferred IDE via control surface.
5. Do NOT treat Hermes terminal cwd as Iris project_root.
6. Named project (e.g. AI guitar tab): `iris_invoke` → `project.open_similar` with `args.query`.
7. Absolute path: `iris_invoke` → `ide.open_folder` with `args.path`.
8. "아이리스 라이트 작업" with no other project name: `project.open_similar` query `iris light`.
9. If open_similar returns ambiguous/low_score: show `matches`, ask user, then `ide.open_folder`.
10. Parents for search come from Iris settings (`project_parents`); inspect via `project.list_parents`.
11. After creating/writing code: `project.write_file` with `open=true` (default live write: empty tab → wait visible → stream chunks into the file). Use `typewriter:false` only for instant dump.
12. On run requests: `project.run` — output in **IDE integrated terminal** (not a log file tab); only summarize in chat.
13. Calendar / 일정: `workspace.open_calendar`, then `calendar.add_event` / `calendar.list_events` / `calendar.select_day` / `calendar.delete_event` (skill iris-calendar).
14. Wiki / 위키에 저장: gather content first, then `wiki.write_user_note` with `title`+`content` (+`source_url`); never claim saved without ok result (skill iris-wiki). Open UI: `workspace.open_obsidian` / `wiki.open_note`.
15. Email / 메일: `workspace.open_email`, then `email.list_messages` (today=true or since=YYYY-MM-DD) / `email.read_message` / `email.open_compose` / `email.send` (skill iris-email). Never invent inbox contents.
16. "기본화면으로" / home / leave email·calendar·Companion: `ide.exit_companion` if needed, then `workspace.open_assistant`.
17. Mic off/on: `voice.mic_off` / `voice.mic_on` (status: `voice.mic_status`). Do not claim mic tools are missing.
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
        and "voice.mic_off" in existing
        and "workspace.open_assistant" in existing
        and "stream chunks" in existing
        and "integrated terminal" in existing
        and "iris-vibe-code" in existing
        and "iris-calendar" in existing
        and "wiki.write_user_note" in existing
        and "email.list_messages" in existing
        and "iris-email" in existing
    ):
        return "memory nudge already present"
    cleaned = _strip_old_nudge(existing) if "iris-control-nudge" in existing else existing
    text = cleaned.rstrip() + ("\n\n" if cleaned.strip() else "") + _BLOCK.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    return "memory nudge updated (v10)"


if __name__ == "__main__":
    print(ensure_memory_nudge())
