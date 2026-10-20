# No console

No console proves Windows console windows (Cascadia / cmd) do not flash when Iris spawns subprocesses from the GUI path.

## Sub-features

- `subprocess-patch` asserts CREATE_NO_WINDOW injection helpers exist and behave.
- `pythonw-control` keeps Hermes iris-control on pythonw when available.
- `emulator-gui-exception` documents DETACHED_PROCESS without CREATE_NO_WINDOW for the Android emulator GUI.

## How to get to it (user POV)

- Send chat text or an image. No console window should flash.
- Restart Iris and repeat once after subprocess-related changes.

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature no-console`
- **Observe.** Exit code `0`. unittest verbose output in evidence stdout.
- **Manual.** After code changes to `win_subprocess` or `__main__` patches, also do one live chat send and watch for a console flash (computer-use or eyes).

## Gotchas

- Emulator GUI must not get CREATE_NO_WINDOW (black screen). Doctoring “no console” must not “fix” that path.
- `shell=True` console commands on the chat hot path regress easily. Prefer argv lists + `no_window_kwargs()`.
