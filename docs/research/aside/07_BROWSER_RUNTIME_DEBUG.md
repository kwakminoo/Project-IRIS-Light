# IRIS × Hermes browser runtime debug

Measured 2026-10-27. Symptom class: Korean chat mojibake, news/Sources instead of the in-window browser, `[재생]` then a generic chat error, and no proof that `browser.*` ran.

## Conclusion

Hermes finished the 14:26 turn without calling `iris_invoke`. It used the visible `web_search` tool, wrote Korean news plus Sources, then IRIS dropped the history and showed `요청을 처리하지 못했습니다` with the cause stripped. `[재생]` is the chat TTS chip, not YouTube play.

Three shipped knobs were wrong or silent:

1. Sidecar stdin/stdout could decode the user line as the Windows locale.
2. Hermes `tool_search` deferred every `mcp-*` tool, so `iris_invoke` was not on the model-visible list. MEMORY also taught the wrong `mcp__iris_control__*` names.
3. `explain_chat_error` swallowed unknown stream/UI errors.

Oct 26 chat rows in `iris_light.db` store Korean correctly. The WebEngine packer also emits Korean PAGE TEXT correctly. The garble is a sidecar/locale path, not Markdown render and not the model inventing `ȭ`.

Live `session.execute` on an isolated Qt WebEngine reached Naver, Naver weather search, and a YouTube IU watch URL with `playing=true`. The running app's Control Surface `GET /v1/state` hung, so a live `iris_invoke` against that GUI was not a pass.

## Confirmed facts

- 14:26:37 composer send, 17 chars, InternalSidecar (no `stage=request` in `iris.log`).
- Hermes `nemotron-3-ultra:cloud` ran `web_search` for Korean daily news. No `iris_invoke`. Finish 1317 chars.
- 14:27:25 IRIS reset history. User and assistant rows for that turn are absent from `iris_light.db`.
- EngineHome `C:\Users\serin\.iris-light\engine\config.yaml` now has `tools.tool_search.enabled: off`. MEMORY is nudge v23 with bare `iris_invoke`.
- Isolated WebEngine 2026-10-27 14:50: `.tmp/live-webengine-scenarios.json`.
- Control Surface listen is PID 55724 (`Python312\pythonw.exe -m iris`), child of venv `pythonw -m iris` 22716. `GET /v1/state` connected and then timed out at 10s.
- Cursor Computer Use sidecar refused launch (`sidecar_unavailable`). Desktop IRIS clicks were not available.

## Structure

```
user chat
  -> MainWindow composer
  -> InternalSidecar NDJSON stdin          [A: locale decode]
       -> Hermes AIAgent tool loop
            -> web_search (was visible)    [B: iris_invoke deferred]
            -> iris_invoke (wanted)
                 -> MCP iris_control_stdio
                 -> POST /v1/invoke        [live GUI hung here]
                 -> control_actions/browser._handle
                 -> BrowserSession.execute
                 -> Qt WebEngine
            -> assistant text + Sources
  -> Hermes SSE / sidecar events
  -> ChatPanel render / TTS [재생]
  -> _on_chat_failed -> explain_chat_error [C: cause stripped]
```

This incident forks at **B** (tool choice) and dies at **C** (error text). **A** is the encoding fork for Korean on the sidecar pipe. WebEngine itself is not on the 14:26 path.

## Code review

| Point | What it did | Why it did not stop this |
|---|---|---|
| `iris/engine/runtime.py` `_sidecar_env` | Spawned the sidecar with the parent env | No `PYTHONUTF8` / `PYTHONIOENCODING`. Windows child stdin could be cp949. |
| `iris/engine/_sidecar_main.py` | Read NDJSON lines and ran `AIAgent` | Streams were not reconfigured to UTF-8 before `json.loads`. |
| Hermes `tools/tool_search.py` | Defers every tool whose toolset starts with `mcp-` | `iris_invoke` left the visible list. The model used `web_search`. |
| `hermes_iris_control_sync.py` | Installed MCP, disabled Hermes `browser`/`terminal` | Did not turn `tool_search` off. |
| `hermes_memory_nudge.py` v22 | Taught `mcp__iris_control__iris_invoke` | Hermes lists `iris_invoke`. The taught name never exists. |
| `iris/mcp/iris_control_stdio.py` | POST `/v1/invoke`, `ensure_ascii=True` JSON | Not reached on the 14:26 turn. |
| `iris/ui/control_actions/browser.py` `_handle` | `parse_command` → `session.execute` → `pack_hermes_result` | Not reached on the 14:26 turn. Isolated execute later proved the path. |
| `ChatPanel` `[재생]` | TTS link on assistant HTML | Not YouTube play. |
| `explain_chat_error` | Mapped known statuses | Unknown text became a generic sentence. |
| `hermes_client.py` SSE | UTF-8 decode | Oct 26 DB Korean is valid. Not the 14:26 garble source. |

Not touched: BrowserSession play budget (90s), mini-player, IDE browser, Hermes planner, a second agent loop, timeout bumps.

## Fix

| File | Change |
|---|---|
| `iris/engine/runtime.py` | `_sidecar_env` sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` |
| `iris/engine/_sidecar_main.py` | `_stdio_utf8()` reconfigures stdin / host stdout / stderr |
| `iris/system/hermes_iris_control_sync.py` | `ensure_hermes_iris_tools_eager()` writes `tools.tool_search.enabled=off` |
| `iris/system/hermes_memory_nudge.py` | v23 teaches `iris_invoke` / `iris_get_state` / `iris_get_catalog` |
| `iris/infrastructure/hermes_errors.py` | unknown errors keep `raw[:240]` |
| tests + `_check_chat_blocks` | lock the four contracts |

## Improvement

The empty place is live `iris_invoke` against the already-open GUI. `/v1/state` hung on the elevated child. Do not raise MCP timeout to hide that. Restart IRIS after this sync so the running Hermes process reloads `tool_search.enabled=off`.

## Borrow

| Name | What to take | Why not this time |
|---|---|---|
| Hermes `tools.tool_search.enabled` | Shipped eager/defer knob | Used. No new discovery layer. |
| Aside / Playwright MCP | Second browser | Forbidden. `session.execute` already drives QWebEngine. |
| Computer Use | Desktop click of the IRIS window | Sidecar unavailable. Isolated WebEngine used instead. |
| New IRIS planner | Observe-Act-Verify class | Hermes already owns the tool loop. |

## Open

- Running Control Surface hung. Live NL chat through the open window was not re-run.
- Naver home packed PAGE TEXT in the isolated run did not include a 로그인 control (likely logged-in chrome or below the excerpt).
- `_check_chat_blocks` WorkspaceIrisPanel smoke still misses `'Python'` in `toHtml()`. Korean Sources assert passed in isolation.
- Hermes gateway process must be restarted before the model sees eager `iris_invoke`.
