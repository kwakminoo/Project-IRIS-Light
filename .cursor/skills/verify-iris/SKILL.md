---
name: verify-iris
description: >-
  Drive and prove Project IRIS Light (PyQt6 desktop) the way a user would.
  Use when proving a change to Iris GUI, chat, IDE companion, control HTTP,
  or Windows no-console contracts; or when asked to verify-iris / control Iris.
---

# verify-iris

Agent-facing control skill for **Iris Light** (primary surface: PyQt6 desktop). Secondary surfaces: local control HTTP (`127.0.0.1` `/v1/invoke`), IRIS IDE Theia bundle, optional Android emulator. This skill is the maintained proof path. Prefer it over ad-hoc UI clicking.

Repo root = workspace containing `iris/` and `.venv/`. Helpers live under `.cursor/skills/verify-iris/scripts/`.

## Launch

Headless feature proofs do not keep a long-lived GUI. They spawn short-lived Qt apps inside `python -m iris.ui._check_*` and exit.

Live desktop (user-path / control HTTP):

```powershell
# Prefer thin launcher (loads workspace source):
.\dist\IRIS.exe
# Or:
.\.venv\Scripts\pythonw.exe -m iris
```

Ready when all of these hold:

- Process owns a MainWindow (not a dead pythonw).
- `%USERPROFILE%\.iris-light\control_port` and `control_token` exist.
- `doctor.py` reports `control.live: true` and `control.ok: true`.

Teardown for processes **this verification run started**: record the PID at launch; stop that PID only. Never `taskkill` by image name. Never stop an Iris the user already had open unless the run marker file proves this run started it (see Cleanup).

Data dir is always `%USERPROFILE%\.iris-light` (no env override in current code). Treat it as a shared singleton.

## Doctor

```powershell
.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\doctor.py
```

Require `ok: true`, `venv_python: true`, `iris_import: true`. For live Drive, also require `control.live: true`. If doctor fails, fix the checkout or start Iris before driving.

## Drive

Layers (use the highest that proves the claim):

1. **Headless `_check_*` / unittest** via `prove_feature.py` (default for CI-like proof).
2. **Live control HTTP** via `invoke.py` when Iris is already up (chat, IDE open folder, project.run). Pattern matches `iris/ui/_check_local_vibe_smoke.py`.
3. **Computer-use / coordinates** only when layers 1 and 2 cannot observe the user-visible result.

```powershell
.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature startup
.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\invoke.py ping
.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\invoke.py ide.open_folder --args "{\"path\":\"C:\\\\tmp\\\\proj\",\"new_window\":true}"
```

Feature recipes: `.cursor/skills/verify-iris/features/`. Read `features/README.md` first, then the feature file. Stable handles are module entry points (`python -m iris.ui._check_*`) and control action names, not pixel coords.

## Evidence

Write under:

`.iris_light_test_tmp/verify-iris/<run_id>/<feature>/`

`prove_feature.py` always writes `report.json`, `stdout.txt`, `stderr.txt`. For live invoke journeys, also save the request JSON and response JSON in that folder.

Proof standards:

- Exercise a real user path or the repo's existing user-path harness (`_check_*`, control actions). Do not call private setters as the only proof.
- Capture action + resulting state (exit code, report fields, side-effect files such as `.iris/last_run.log`).
- Mocks only where production already isolates the boundary (control HTTP contract test uses a temp port and does not write `~/.iris-light` endpoints).

## Cleanup

- Headless proves: no process left; do not delete evidence.
- Live Iris started by this run: kill the recorded PID only; leave `~/.iris-light` DB/wiki alone unless the feature recipe names disposable scratch under a temp folder.
- Never delete `.iris_light_test_tmp/verify-iris/**` as part of cleanup.

## Isolate

Iris shares one `%USERPROFILE%\.iris-light` (DB, control_port, token, wiki). Two agents must not live-drive the same instance. If `control.live` is true and you did not start that process in this run, either:

- use headless features only, or
- refuse live Drive and report the conflict.

Do not invent a second HOME without a product env var (none exists today).

## Helpers

| Script | Role |
|---|---|
| `scripts/doctor.py` | Read-only health JSON |
| `scripts/prove_feature.py --feature <id>` | Run mapped headless feature + evidence |
| `scripts/invoke.py <action> [--args JSON]` | Live `/v1/invoke` |

Feature IDs known to `prove_feature.py`: `startup`, `companion-tile`, `control-http`, `chat-stop`, `file-drop`, `no-console`.
