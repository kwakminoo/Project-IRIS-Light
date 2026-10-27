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
