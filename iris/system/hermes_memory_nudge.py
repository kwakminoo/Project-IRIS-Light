"""Ensure Hermes MEMORY mentions Iris Control tools (optional nudge)."""



from __future__ import annotations



import re



from iris.system.hermes_iris_control_sync import hermes_home



_MARKER = "<!-- iris-control-nudge-v15 -->"

_BLOCK = """<!-- iris-control-nudge-v15 -->

## Iris Light UI control

When the user asks to open IDE / start coding / Companion / "ide 켜줘" / open a project / 아이리스 라이트 작업 시작:

1. Prefer MCP tools with EXACT names: `mcp__iris_control__iris_get_state`, `mcp__iris_control__iris_get_catalog`, `mcp__iris_control__iris_invoke` (skills: iris-work-start, iris-work-end, iris-session-status, iris-vibe-code, iris-calendar, iris-wiki, iris-email). Never invent bare `iris_invoke` without the mcp__iris_control__ prefix.

2. "ide 켜줘" / open IDE only: `mcp__iris_control__iris_invoke` → action=`ide.enter_companion`.

3. Do NOT use terminal `cursor`/`code` alone — that skips Iris Companion tiling.

4. Do NOT claim Iris has no IDE GUI — Iris launches the preferred IDE via control surface.

5. Do NOT use Hermes built-in `terminal` tool for project commands — it is disabled for Iris. ALWAYS `mcp__iris_control__iris_invoke` → action=`project.run` so output appears in the **bound IDE integrated terminal**.

6. Do NOT treat Hermes terminal cwd as Iris project_root.

7. Named project (e.g. AI guitar tab / 자료구조 / 동양미래대학교): `mcp__iris_control__iris_invoke` → action=`project.open_similar` args=`{query}`.

8. Absolute path: `mcp__iris_control__iris_invoke` → action=`ide.open_folder` args=`{path}`.

9. "아이리스 라이트 작업" with no other project name: `project.open_similar` query `iris light`.

10. If open_similar returns ambiguous/low_score: show `matches`, ask user, then `ide.open_folder`.

11. Parents for search come from Iris settings (`project_parents`); inspect via `project.list_parents`.

12. After creating/writing code: `project.write_file` with `open=true` (default live write: empty tab → wait visible → stream chunks into the file). Use `typewriter:false` only for instant dump.

13. On run/npm/pip/python/node/shell requests: **only** `project.run` — full output in IDE terminal; chat summary only.

14. Calendar / 일정: `workspace.open_calendar`, then `calendar.add_event` / `calendar.list_events` / `calendar.select_day` / `calendar.delete_event` (skill iris-calendar).

15. Wiki / 위키에 저장: Iris may handle locally (file chip + save intent). Else PDF·URL·파일 → `wiki.import_content` (`source`, `mode=raw|summarize`); manual → `wiki.write_user_note`; never claim saved without ok (skill iris-wiki).

16. Email / 메일: `workspace.open_email`, then `email.list_messages` (today=true or since=YYYY-MM-DD) / `email.read_message` / `email.open_compose` / `email.send` (skill iris-email). Never invent inbox contents.

17. "기본화면으로" / home / leave email·calendar·Companion: `ide.exit_companion` if needed, then `workspace.open_assistant`.

18. Mic off/on: `voice.mic_off` / `voice.mic_on` (status: `voice.mic_status`). Do not claim mic tools are missing.

19. If `mcp__iris_control__*` tools are missing from your tool list: tell the user Iris Control MCP is offline (Iris app must be running; restart Hermes gateway), do not invent tool calls.

20. Open a file only with `ide.open_file` after `iris_get_state` and `project.list_files`. Relative `path` is the bound workspace, not the shell cwd. The folder action is `ide.open_folder` (there is no project.open_folder). If the file is missing, say so. Do not create another file or say it opened.

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

        and "mcp__iris_control__iris_invoke" in existing

        and "voice.mic_off" in existing

        and "workspace.open_assistant" in existing

        and "stream chunks" in existing

        and "integrated terminal" in existing

        and "Hermes built-in" in existing

        and "iris-vibe-code" in existing

        and "iris-calendar" in existing

        and "wiki.write_user_note" in existing

        and "wiki.import_content" in existing

        and "handle locally" in existing

        and "email.list_messages" in existing

        and "iris-email" in existing

        and "tools are missing" in existing

        and "there is no project.open_folder" in existing

    ):

        return "memory nudge already present"

    cleaned = _strip_old_nudge(existing) if "iris-control-nudge" in existing else existing

    text = cleaned.rstrip() + ("\n\n" if cleaned.strip() else "") + _BLOCK.strip() + "\n"

    path.write_text(text, encoding="utf-8")

    return "memory nudge updated (v15)"





if __name__ == "__main__":

    print(ensure_memory_nudge())


