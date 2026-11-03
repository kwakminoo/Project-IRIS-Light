# Startup

Startup proves Iris can construct and show `MainWindow` in test mode fast enough for a usable desktop shell, then close cleanly without leaving a window.

## Sub-features

- `startup-init` builds `MainWindow(test_mode=True)` under 8 seconds.
- `startup-show` processes events after `show()` without abort.
- `startup-close` closes the window and drains events.

## How to get to it (user POV)

- Double-click `dist\IRIS.exe` or run `.venv\Scripts\pythonw.exe -m iris` and wait for the main shell.
- Agents prove the same init path via the headless check (no lasting window).

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.
- No need for a live Iris control port.

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature startup`
- **Observe.** Exit code `0`. `report.json` has `"ok": true`. stdout contains `iris_startup ok`.
- **Evidence.** Folder `.iris_light_test_tmp/verify-iris/<run_id>/startup/` retains `report.json`, `stdout.txt`, `stderr.txt` after the process exits.

## Gotchas

- Qt slot exceptions abort with `0xC0000409` and often leave empty launcher logs. A hang or crash here is a real failure.
- After `iris_startup ok` prints, process exit may still be `0xC0000005` during Qt teardown. `prove_feature.py` treats the success marker as pass. Missing the marker is a fail.
- `ensure_qt_webengine_ready()` must run before WebEngine imports. The check already calls it.
- Passing this check does not prove Hermes login or live chat. Those need other features.
