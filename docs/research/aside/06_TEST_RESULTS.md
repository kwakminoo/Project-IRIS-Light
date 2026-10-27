# Browser stability test results

Reference for the READY / crash / play-budget change. Measured 2026-10-27 on this workspace.

## What changed

| File | Change |
|---|---|
| `iris/browser/_driver.py` | `remaining_wait`, `_wait_load` for navigate and reload, crash latch, Fake `queue_wait` / `crash`, no URL-to-READY promotion |
| `iris/browser/session.py` | 90s play `deadline`, FAULTED same-URL is not idempotent, idle FAULTED `snapshot()` publishes once |
| `iris/ui/window/top_status_header.py` | FAULTED chip tooltip from `last_error` |
| `tests/browser/test_browser_session_unit.py` | `SessionWaitAndCrashTests` |

`iris/ui/browser/webengine_setup.py` still only logs `renderProcessTerminated`. Phase is written on the driver.

Reload default wait stays 30s. Navigate stays 45s. Phase strings stay `closed|opening|ready|busy|faulted`. No `LOADING`. Packer keys unchanged.

## Commands

```
.venv\Scripts\python.exe -m unittest tests.browser.test_browser_session_unit tests.browser.test_browser_agent tests.browser.test_browser_intent tests.browser.test_browser_registry_sync
.venv\Scripts\python.exe -m iris.browser._check_intent
.venv\Scripts\python.exe -m iris.system._check_browser_scenarios
.venv\Scripts\python.exe -m iris.ui.browser._check_webengine_setup
.venv\Scripts\python.exe -m iris.ui.browser._check_mini_player
```

## Results

| Check | Result |
|---|---|
| `tests.browser.test_browser_session_unit` (includes `SessionWaitAndCrashTests`) | pass, 62 tests in the combined unittest run |
| `tests.browser.test_browser_agent` | pass |
| `tests.browser.test_browser_intent` | pass |
| `tests.browser.test_browser_registry_sync` | pass |
| Combined unittest | OK, 62 tests, 1.822s |
| `iris.browser._check_intent` | `browser intent ok` |
| `iris.system._check_browser_scenarios` | fixture A–C plus `webengine smoke navigate+scroll ok` |
| `iris.ui.browser._check_webengine_setup` | `webengine_setup ok` |
| `iris.ui.browser._check_mini_player` | fixture toggle, Qt reparent, chat pip |

## Cases `SessionWaitAndCrashTests` covers

- Reload success stays READY.
- Reload timeout and navigate timeout return `ok=False`, phase FAULTED.
- Navigate success records BUSY on the Fake `phases_seen` list.
- Search+play still plays on the YouTube fixture.
- Search+play with a second-wait timeout is FAULTED and does not call `try_play`.
- After a successful watch load, a spent play budget stays READY with `play timed out. Try search again.`
- Idle crash publishes FAULTED and a reload hint in `last_error`.
- Crash during reload is FAULTED.
- `NormalTermination` is not a fault.
- Same-URL navigate after FAULTED is not `idempotent`.

## Not run

- Live YouTube (`IRIS_BROWSER_LIVE=1`).
- A real Chromium renderer kill. Crash is tested through `FakePageDriver.crash()` and a queued `"crash"` wait.
- Hermes `iris_invoke` against a live gateway.

Qt display was available. The WebEngine smoke used a local HTML file, not the network.

## iframe + ref scroll (2026-10-27)

Parent-walk contract. `setRunsOnSubFrames` stays False. Same-origin iframe nodes come from `contentDocument`. Cross-origin frames are listed only as `FrameInfo` with `reachable=False` and `reason=cross_origin`. `browser.scroll` accepts optional `{ref}` and uses `scrollIntoView`. Missing or disconnected `lastEls` entries return `stale_ref` with `ok=False` and no FAULTED phase.

### Files

| File | Change |
|---|---|
| `iris/browser/types.py` | `PageNode.frame`, `PageNode.in_view`, `FrameInfo`, `BrowserSnapshot.frames`, `Scroll.ref` |
| `iris/browser/_bridge.js` | Same-origin iframe walk, `frames`, `in_view`, `scrollTo`, connected-ref checks |
| `iris/browser/registry.py` | `_parse_scroll` reads optional `ref` |
| `iris/browser/session.py` | Stamp copies frame and in_view. LookupError on click, type, and scroll-to-ref stays READY |
| `iris/browser/_driver.py` | Snapshot frames, `scroll_by(ref=)`, Fake `mark_disconnected`, no FAULT on ref miss |
| `iris/browser/observation.py` | Node line extras. Trusted `frames=` line |
| `iris/browser/_check_bridge_frames.py` | Local HTML WebEngine check |
| `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` | scroll `{ref}`, frames, disconnected `stale_ref` |
| `tests/browser/test_browser_session_unit.py` | Parse, scroll-to-ref, gen stale, disconnected hook |
| `tests/browser/test_browser_intent.py` | PAGE TEXT frame and `in_view=false` lines |

### Commands

```
.venv\Scripts\python.exe -m unittest tests.browser.test_browser_session_unit tests.browser.test_browser_agent tests.browser.test_browser_intent tests.browser.test_browser_registry_sync
.venv\Scripts\python.exe -m iris.browser._check_intent
.venv\Scripts\python.exe -m iris.system._check_browser_scenarios
.venv\Scripts\python.exe -m iris.browser._check_bridge_frames
```

### Results

| Check | Result |
|---|---|
| Combined unittest | pass, 67 tests, 2.110s |
| `iris.browser._check_intent` | `browser intent ok` |
| `iris.system._check_browser_scenarios` | fixture A–C plus `webengine smoke navigate+scroll ok` |
| `iris.browser._check_bridge_frames` | pass. Qt display present |
| `iris.ui.browser._check_mini_player` | pass (regression; not modified) |

### WebEngine evidence

The check writes `.tmp/browser-frames/frames.html` and `same.html`. Log: `.tmp/browser-frames/run.log`.

Observed on the local file URL:

- Same-origin node `g3e2 button Inner Submit frame=f0`
- Cross-origin `f1` origin `https://example.com`, `reachable=False`, `reason=cross_origin`
- Trusted line `frames=f0:file://:ok,f1:https://example.com:cross_origin`
- PAGE TEXT and excerpt have no `Example Domain` and no `SAME_ORIGIN_SECRET`
- `Below Fold` starts `in_view=false`. Scroll `{ref}` brings it into view
- Click after `remove-me` is removed returns `stale_ref`, phase READY
- Click after reload on the old ref returns `stale_ref`, phase READY

`setRunsOnSubFrames(False)` is unchanged. Mini player, ViewHost, Hermes toolset disable, and MCP 120s were not touched.

## Packed snapshot PAGE TEXT (2026-10-27)

Base is candidate-1 compact `PageNode` flags. The packer grafts C2 excerpt elasticity only. `lastEls[i]` stays the printed node. No `LandmarkRaw`, no `PageTextPlan`, no packer-omitted refs, no `value=` suffix.

### Files

| File | Change |
|---|---|
| `iris/browser/types.py` | `CTX_CAP`, `PageNode` flags and `context` |
| `iris/browser/_bridge.js` | `accName`, `contextOf`, `flagState`, input-type role hint. `textOf` unchanged |
| `iris/browser/_driver.py` | Mapper copies flags. Fake `scroll_by` uses `dataclasses.replace` |
| `iris/browser/session.py` | `_stamp` is the only ref writer and clips `name` / `context` |
| `iris/browser/observation.py` | True-only suffixes, `ctx=` on `(role, name)` collision, `PAGE_TEXT_BUDGET` |
| `iris/browser/_check_bridge_snapshot.py` | Local HTML WebEngine check |
| `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` | `ctx=` and true-only flags |
| `tests/browser/test_browser_intent.py` | Packer lines, password, dense excerpt, context out of HUD |
| `tests/browser/test_browser_session_unit.py` | Idle snapshot does not restamp. Stamp copies flags |
| `tests/browser/test_browser_agent.py` | Packer key set locked |

### Commands

```
.venv\Scripts\python.exe -m unittest tests.browser.test_browser_session_unit tests.browser.test_browser_agent tests.browser.test_browser_intent tests.browser.test_browser_registry_sync
.venv\Scripts\python.exe -m iris.browser._check_intent
.venv\Scripts\python.exe -m iris.system._check_browser_scenarios
.venv\Scripts\python.exe -m iris.browser._check_bridge_snapshot
.venv\Scripts\python.exe -m iris.browser._check_bridge_frames
```

### Results

| Check | Result |
|---|---|
| Combined unittest | pass, 73 tests, 2.263s |
| `iris.browser._check_intent` | `browser intent ok` |
| `iris.system._check_browser_scenarios` | fixture A–C plus `webengine smoke navigate+scroll ok` |
| `iris.browser._check_bridge_snapshot` | pass. Qt display present |
| `iris.browser._check_bridge_frames` | pass. iframe locked lines unchanged |
| `iris.ui.browser._check_mini_player` | pass (regression; not modified) |
| Live YouTube (`IRIS_BROWSER_LIVE=1`) | not-run |
| Hermes `iris_invoke` against a live gateway | not-run |

### PAGE TEXT before / after

Before, on the same login-shaped page, icon buttons dropped, two Submit lines were identical, and state was invisible:

```
BEGIN PAGE TEXT (untrusted input data): https://example.test/login
title=Sign in
g1e0 button Submit
g1e1 button Submit
g1e2 textbox Remember me
g1e3 button Disabled Save
excerpt=Sign in …
END PAGE TEXT: https://example.test/login
```

After, from `.tmp/browser-snapshot/run.log` on the local file URL:

```
BEGIN PAGE TEXT (untrusted input data): file:///C:/Users/serin/Github/Project-IRIS-Light/.tmp/browser-snapshot/snapshot.html
title=IRIS snapshot
g3e0 h1 Login
g3e1 button Menu
g3e2 button Submit ctx=login
g3e3 button Submit ctx=signup
g3e4 button Inner Submit frame=f0
g3e5 checkbox Remember me in_view=false checked
g3e6 button Disabled Save in_view=false disabled
g3e7 textbox Password in_view=false
g3e8 button Below Fold in_view=false
excerpt=Login login Submit signup Submit Remember meDisabled SavePassword Below Fold
END PAGE TEXT: file:///C:/Users/serin/Github/Project-IRIS-Light/.tmp/browser-snapshot/snapshot.html
```

Locked iframe lines from `_check_bridge_frames` stayed exact:

`g3e2 button Inner Submit frame=f0`

`g3e3 button Below Fold in_view=false`

`Menu` comes from `aria-label`. Duplicate Submit lines carry `ctx=`. Checkbox and disabled print only when true. `hunter2` and `SAME_ORIGIN_SECRET` are absent. Unique `Menu` has no `ctx=` even though the bridge sent a heading token. Packer keys stay `ok, command_kind, detail, trusted, page_text, url, phase, playing, gen`. Hostile titles stay out of `trusted`. `setRunsOnSubFrames(False)` is unchanged. Mini player, ViewHost, Hermes toolset disable, and MCP 120s were not touched.

## Idle snapshot page identity (2026-10-27)

Cause: `BrowserSession.snapshot()` overlaid live URL/title and kept the previous `gen`/`nodes`. `BrowserPanel._on_tab_changed` calls that idle path after `setPage`. Chat POST then packed the old refs against the new document.

Fix: restamp when `live.url` or `tab_index` differs. Same-page idle snapshot still keeps refs. Extract/media still skip stamp. No new cache type.

| Check | Result |
|---|---|
| Same-page idle snapshot | pass (gen and refs unchanged) |
| Driver-only URL change then idle snapshot | pass (new gen, new nodes, old click `stale_ref` READY) |
| Watch then back to React via idle snapshot | pass |
| `tab_index` change, same URL | pass |
| Combined unittest | pass, 76 tests, 2.202s |
| `_check_intent` / `_check_browser_scenarios` | pass |
| `_check_bridge_snapshot` / `_check_bridge_frames` | pass |

Not run: two live Qt tabs in the panel (unit test uses Fake driver + `current_tab_index`). SPA same-URL DOM replace without a tab or URL change is unmeasured; `browser.snapshot` still restamps.

## Hermes multi-step (2026-10-27)

Judgment: existing Hermes tool loop plus `session.execute` already cover Observe → Act → Verify. No product code was added.

### Path (read, not reimplemented)

| Step | Owner | File |
|---|---|---|
| Tool loop, iteration budget | Hermes | `%LOCALAPPDATA%\hermes\...\workspace\agent\turn_tool_round.py`, `turn_finalizer.py` |
| Disable Hermes `browser`/`terminal` | IRIS | `iris/system/hermes_iris_control_sync.py` |
| MCP tools | IRIS | `iris/mcp/iris_control_stdio.py` (`urlopen` 120s) |
| Sensitive HUD | IRIS | `looks_sensitive_browser_act` → `ask_human` → `session.execute` |
| Packed result | IRIS | `pack_hermes_result` |
| Recipes / stale_ref teaching | IRIS | `command_recipes()`, `browser_teaching_block()` |
| Chat cancel | IRIS | `HermesChatWorker.request_cancel` stops SSE only |

### Case matrix

| Case | Result | Evidence |
|---|---|---|
| Search → result → click | pass | `test_search_then_click` |
| Page change → snapshot restamp → click | pass | idle snapshot tests after `ee68fce` |
| `stale_ref` then re-query | pass | `test_stale_ref_after_snapshot_and_reload`, disconnected-ref tests |
| Duplicate buttons | pass | PAGE TEXT `ctx=` in `test_browser_intent` and `_check_bridge_snapshot` |
| iframe click / scroll | pass | `_check_bridge_frames` |
| Per-command timeout | pass | `SessionWaitAndCrashTests` (navigate 45s, reload 30s, play 90s) |
| Hermes iteration cap | existing, not IRIS | `max_iterations` default `sys.maxsize`; `IterationBudget` in Hermes |
| User cancel of the chat stream | existing | `request_cancel` sets the cancel token and stops SSE |
| In-flight `session.execute` abort | not implemented | cancel does not interrupt an open navigate/play |
| Sensitive act HUD | pass | `test_looks_sensitive_browser_act` |
| Combined unittest | pass, 76 tests, 2.057s | 2026-10-27 rerun, no code change |
| Live Hermes play | skip | `_check_browser_hermes_play`: gateway streamed, then 45s budget on `gemma4:e2b` |
| Two live Qt tabs in the panel | not-run | Fake driver covers tab_index |
| SPA same-URL DOM replace | unmeasured | `browser.snapshot` still restamps |

### Not added

- IRIS planner / Observe-Act-Verify class
- Second agent framework
- Extra browser engine
- Per-turn IRIS command counter
- Arbitrary JavaScript execute
- In-flight execute abort

Phase 2 screenshot fallback, Phase 3 result events, Phase 4 secret fill, Phase 5 ephemeral profile, and Phase 6 site notes stay later work. They are not required for Hermes to chain `browser.*` commands.

## Chat encoding + tool visibility (2026-10-27)

Cause and path: `docs/research/aside/07_BROWSER_RUNTIME_DEBUG.md`.

### Commands

```
.venv\Scripts\python.exe -m unittest tests.test_iris_engine_turn_pipe tests.test_hermes_iris_control_sync
.venv\Scripts\python.exe -m iris.infrastructure.hermes_errors
.venv\Scripts\python.exe -m unittest tests.browser.test_browser_session_unit tests.browser.test_browser_agent tests.browser.test_browser_intent tests.browser.test_browser_registry_sync
.venv\Scripts\python.exe -m iris.browser._check_intent
.venv\Scripts\python.exe -m iris.system._check_browser_scenarios
.venv\Scripts\python.exe -m iris.ui.browser._check_mini_player
.venv\Scripts\python.exe -m iris.browser._check_bridge_snapshot
.venv\Scripts\python.exe -m iris.browser._check_bridge_frames
```

### Results

| Check | Result |
|---|---|
| `SidecarUtf8EnvTests` | pass |
| `tests.test_hermes_iris_control_sync` (`tool_search.enabled=off`, MEMORY `iris_invoke`) | pass |
| Combined turn-pipe + sync | OK, 10 tests, 2.819s |
| `hermes_errors` unknown text keeps `incomplete chunk after Sources` | pass |
| Korean + Sources `iris_message_to_chat_html` | pass (isolated `_assert_error_and_user`) |
| Combined browser unittest | OK, 76 tests |
| `_check_intent` | `browser intent ok` |
| `_check_browser_scenarios` | fixture A–C plus webengine smoke |
| `_check_mini_player` | pass |
| `_check_bridge_snapshot` | pass |
| `_check_bridge_frames` | pass |
| Isolated live WebEngine Naver open | pass, `https://www.naver.com/`, Korean PAGE TEXT |
| Isolated live WebEngine Naver weather | pass, title `오늘 날씨 : 네이버 검색` |
| Isolated live YouTube `아이유 노래` play | pass, `playing=true`, `ad_playing`, watch URL |
| Isolated stale click | pass, `ok=false`, `detail=stale_ref`, phase READY |
| `explain_chat_error("incomplete chunk after Sources")` | keeps the raw cause |

### Not run / not pass

| Check | Why |
|---|---|
| Desktop IRIS chat scenarios 1–6 through the open window | Cursor Computer Use sidecar_unavailable |
| Live Control Surface `iris_invoke` | `GET /v1/state` on 127.0.0.1:8765 connected then timed out. Listener is Python312 `pythonw -m iris` PID 55724 |
| Live Hermes NL (`_check_browser_hermes_play`) | Not re-run. Prior skip: 45s budget on `gemma4:e2b`. Gateway is up |
| Naver home “로그인 버튼” in packed PAGE TEXT | Isolated snapshot had no 로그인 token in the excerpt |
| Full `python -m iris.ui.chat._check_chat_blocks` | WorkspaceIrisPanel smoke: missing `'Python'` in `toHtml()`. Korean assert is not that failure |

Evidence file: `.tmp/live-webengine-scenarios.json`. EngineHome already has `tools.tool_search.enabled: off` and MEMORY v23. Restart the running Hermes/IRIS process before treating NL chat as fixed.
