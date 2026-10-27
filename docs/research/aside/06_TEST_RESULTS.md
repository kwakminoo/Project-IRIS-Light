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
