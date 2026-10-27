# Unit 7 live IRIS predicate

Date: 2026-10-27. Workspace HEAD at start was 06fd9b5. After the session HEAD is 170dbcc (later engine commits landed while this run was open). Desktop `IRIS.lnk` TargetPath is `C:\Users\serin\Github\Project-IRIS-Light\dist\IRIS.exe`. Computer-use MCP refused (`sidecar_unavailable`). Live UI drive used control-surface HTTP, process lists, SQLite, and GDI screenshots.

## Install (before launch)

First `install_into` on `C:\Users\serin\.iris-light\engine` failed. `uv sync --extra homeassistant` died because the pin SHA `4787e4d` does not declare that extra. Pip extras then reported success without `aiohttp`. Probe discarded staging.

Second install dropped the unknown extra. `uv sync` returned 0 but wrote packages into `.venv`. Probe still read `venv\Scripts\python.exe` and failed with `No module named 'hermes_cli'`.

Third install after extras filter plus `UV_PROJECT_ENVIRONMENT=venv` / `--active` succeeded. `live_check.py` then reported `probe_ok: true`. A throwaway `shared_engine().ensure_ready()` returned `EngineReady` and spawned sidecar pid 16624. `shutdown` killed it.

Those install fixes are already in `61907e8` and `57ba1e7`. This run did not add another commit.

## Scenario results

| # | Scenario | Result |
|---|---|---|
| 1 | IRIS-only launch, auto-init, no new :8642 | **PASS** |
| 2 | Chat without an external Hermes server | **PASS** (sidecar; composer send from the live driver did not land) |
| 3 | Ollama agent reply, or sidecar reach if Ollama down | **PASS** (headless `shared_engine` turn) |
| 4 | YouTube search/play and mini-player | **PASS** (control surface, not composer) |
| 5 | Multi-tool sequence | **PASS** (control surface) |
| 6 | Session/history stays IRIS SQLite | **PASS** |
| 7 | Cancel or forced agent error does not kill Qt | **PASS** (stop + no crash. No in-slot 0xC0000409 repro) |
| 8 | Quit leaves no :8642 from this app | **PASS** |
| 9 | IDE / calendar / chat / mini-player still present | **PASS** (state + UI chrome) |

### 1. Launch and ready

Measured. Shortcut started `dist\IRIS.exe` → `.venv\Scripts\pythonw.exe -m iris` (pid 53920 → 45424). Window title `IRIS`. Health spawned `~\.iris-light\engine\hermes-agent\venv\Scripts\python.exe ...\_sidecar_main.py`. Live Activity showed `engine is ready`. Control state `hermes_online: true`. The only `:8642` listener was leftover pid 13276, python, start 2026-10-18 17:03:44. IRIS did not bind a new listener.

### 2. Chat without external Hermes

The live agent path is the internal sidecar, not HTTP `:8642`. Composer send from the live driver never landed (`SetForegroundWindow` lost to Cursor). `chat_messages` gained no 2026-10-27 user row. A later headless `shared_engine().run_turn` on `gemma4:e2b` streamed `ContentDelta pong` and `TurnFinished pong` with no `:8642`. That is the default chat path the workers now use.

### 3. Ollama / sidecar reach

Pass. Ollama answered `GET http://127.0.0.1:11434/api/tags` with `gemma4:e2b`. IRIS health spawned EngineHome `_sidecar_main.py`. The headless turn in `.tmp/hermes-internal-engine/live_turn.py` used `provider=custom` + `http://127.0.0.1:11434/v1` and finished `pong`. The live picker model `nemotron-3-ultra:cloud` was not the turn that proved Ollama.

### 4. YouTube and mini-player

Pass. `POST /v1/invoke` `browser.search` `{engine:youtube, query:never gonna give you up, play:true}` opened `https://www.youtube.com/watch?v=dQw4w9WgXcQ` with `browser_playing: true`. `browser.mini_player` `{on:true}` succeeded. After returning to assistant, state had `mini_player: true`.

### 5. Multi-tool

Pass as a live tool sequence on the running app. Search/play, then mini-player, then `browser.media` pause (`browser_playing: false`). Not proven as one agent turn that called several tools.

### 6. SQLite history

Pass. Launch created `chat_conversations.id=41` at `2026-10-27T11:17:11`. No Hermes session id column. History stays `~\.iris-light\iris_light.db`.

### 7. Cancel / error vs Qt

Pass for the cases run. `chat.stop` returned ok. IRIS pid 45424 stayed up after the sidecar child was gone. Close used `WM_CLOSE`, not a crash. Did not inject a failing turn into a Qt slot, so 0xC0000409 is not positively reproduced.

### 8. Quit

Pass. After `WM_CLOSE`, no `-m iris` process and no `_sidecar_main.py`. `:8642` is still only leftover 13276 from 2026-10-18. That listener is not this app.

### 9. Smoke surfaces

Pass. Control state had `calendar.selected_day=2026-10-27`, `workspace_mode=assistant`, `preferred_ide=iris_ide`, `mini_player` flag, chat session list in the screenshot. Did not rebuild iris-ide. Companion was not attached (`ide_attached: false`).

## Remaining gaps

- `backend_call._hermes` still talks HTTP (`http://127.0.0.1:8642/v1`). Titles and routines can still take that path.
- Settings / some sync helpers still default to HermesHome when `home=` is omitted.
- Boot still calls `_begin_hermes_update_check`.
- Agent composer turn was not completed in this run (computer-use down, focus steal).
- Leftover `:8642` pid 13276 is still listening. It predates this unit. Do not treat it as IRIS-internal.

## How to rerun

```
.venv\Scripts\python.exe .tmp\hermes-internal-engine\live_check.py
.venv\Scripts\python.exe .tmp\hermes-internal-engine\live_invoke.py state
```

Shortcut check:

```
(New-Object -ComObject WScript.Shell).CreateShortcut("$env:USERPROFILE\Desktop\IRIS.lnk").TargetPath
```
