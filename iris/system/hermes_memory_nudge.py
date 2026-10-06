"""Ensure Hermes MEMORY mentions Iris Control tools (optional nudge)."""



from __future__ import annotations



import re



from iris.system.hermes_iris_control_sync import hermes_home



_MARKER = "<!-- iris-control-nudge-v21 -->"

_BLOCK = """<!-- iris-control-nudge-v21 -->

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

12. After creating/writing code: `project.write_file` with `open=true` (default live write: empty tab → wait visible → stream chunks into the file). `rel_path` is the filename the user asked for. If they did not name a file, ask before writing. Do not invent `iris_generated.py`. Use `typewriter:false` only for instant dump.
12b. Rename: `project.rename_file` with `path` (current relative path) and `new_path`. Find `path` with `project.list_files` or the open editor. If either path is unknown, ask. Do not claim the name changed unless ok.

13. On run/npm/pip/python/node/shell requests: **only** `project.run` — full output in IDE terminal; chat summary only. Keyword auto-run is off while Hermes is on.

14. Calendar / 일정: `workspace.open_calendar`, then `calendar.add_event` / `calendar.list_events` / `calendar.select_day` / `calendar.delete_event` (skill iris-calendar).

15. Wiki / 위키에 저장: no keyword shortcut while Hermes is on. PDF·URL·파일 → `wiki.import_content` (`source`, `mode=raw|summarize`); 직전 답변 → `wiki.write_user_note`; never claim saved without ok (skill iris-wiki). 여러 페이지·사이트 전체는 `wiki.import_pages` (`source` 또는 `sources`, `discover=true`). 페이지마다 `import_content` 를 반복하지 말 것. 저장 성공은 반환의 saved 건수로만 말한다. rel_path 를 비우면 사용자·학습자료·인사이트·projects·research 로 분류된다. inbox 를 기본 경로로 넣지 말 것. 저장된 노트는 `wiki.search`. 이미 있는 노트를 폴더로 옮기거나 분류하면 `wiki.move_notes` (`sources`, `dest_folder`). 같은 바이트를 복사한 뒤 원본을 지운다. `wiki.write_user_note` 로 본문을 다시 쓰지 말 것. `wiki.list_notes` 의 total 이 전체다. truncated 이면 그 페이지만 정리해도 완료가 아니다.
15b. PDF for a submission or a combined note/code (not a wiki save): `note.export_pdf` with `content` and/or `sources` (file paths) and optional `path`. This tool is the save path while Hermes is on. Relative path is under the open project. Do not run pdf_create.py, reportlab, or PyMuPDF yourself — that can kill the Iris process. Do not claim saved unless ok and the file exists. Do not write .pdf via project.write_file.
15c. GitHub MCP/Skill URL: `extension.install_github` (`url`, `kind=auto|mcp|skill`, `scope=project|iris`). In IRIS IDE, scope=project writes the open project only. scope=iris (Hermes) only from the main Iris screen, not from IDE. If status is needs_input, ask for the missing key or directory. Do not invent secrets. Do not claim installed without a URL and ok. Do not say an Open VSX extension and a Hermes MCP were installed together.
15f. Open VSX for the project open in IRIS IDE: `ide.marketplace_search` (`query`) then `ide.marketplace_install` (`id` as publisher.name). Install downloads the VSIX into the IDE deployedPlugins folder. Do not claim installed unless ok and result.package exists. Do not say a PDF tab is already open. If reload is reloaded, say the IDE is restarting to load the extension. If reload is not_running, say it loads the next time IRIS IDE starts. plugin.loaded true is the only signal the plugin host has the extension. Do not say a viewer opened when loaded is false. Name-only requests are not installed. Project plan/progress: `ide.project_log` (`plan`, `decision`, `issue`, `progress`).
15g. Read and change the open IRIS IDE like an editor, not from an empty success: `ide.diagnostics` (reported false is not "no problems"), `ide.symbols`, `ide.references`, `ide.definition`, `ide.edit` (via=editor is the buffer; via=disk applied=append is not a selection replace), `ide.save`, `ide.task`, `ide.debug` (start needs a launch name; no session is not success). Do not claim a fix, a save, or a debug session without ok.
15d. Image attachment → code file: `project.write_image_code` (`image` path, `rel_path`). If the target file is unknown, ask. Never claim the file was written without ok.
15e. If the user message contains `[자료 본문]`, answer from that excerpt (PDF, folder, file, or link). Do not ask for page screenshots first. Do not say you cannot read PDF. HWP is unsupported. Saving a chat as a PDF file stays 15b (`note.export_pdf` only).

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

        and "wiki.search" in existing

        and "wiki.move_notes" in existing

        and "note.export_pdf" in existing

        and "extension.install_github" in existing

        and "project.write_image_code" in existing

        and "[자료 본문]" in existing

        and "no keyword shortcut" in existing

        and "email.list_messages" in existing

        and "iris-email" in existing

        and "tools are missing" in existing

        and "there is no project.open_folder" in existing

        and "ide.diagnostics" in existing

        and "project.rename_file" in existing

    ):

        return "memory nudge already present"

    cleaned = _strip_old_nudge(existing) if "iris-control-nudge" in existing else existing

    text = cleaned.rstrip() + ("\n\n" if cleaned.strip() else "") + _BLOCK.strip() + "\n"

    path.write_text(text, encoding="utf-8")

    return "memory nudge updated (v21)"





if __name__ == "__main__":

    print(ensure_memory_nudge())


