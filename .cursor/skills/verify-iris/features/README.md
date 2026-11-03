# Iris Light verification map

Maintained source for verifying user-facing Iris Light behavior. Read this index, then the matching feature file.

## Baseline preconditions

- Repo root has `.venv\Scripts\python.exe` and the `iris` package imports.
- Run `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\doctor.py` and require `ok: true`.
- Prefer headless features. They do not need a long-lived Iris window.
- Live control features require a running Iris that wrote `%USERPROFILE%\.iris-light\control_port` and `control_token`.
- Never live-drive an Iris instance another agent or the user is actively using for unrelated work without asking. Shared data dir has no second profile.

## Driving conventions

- Start from baseline unless a feature lists extra preconditions.
- Prefer `prove_feature.py` and control action names over screen coordinates.
- Treat commands as literal.
- After a mutation via live control, confirm a second observable (file, DB row, HTTP result field), not only `ok: true`.
- Keep proof artifacts under `.iris_light_test_tmp/verify-iris/`. Cleanup must not remove them.

## Proof and skip reporting

- Capture the command, exit code, and `report.json` (or invoke request/response).
- An unreachable live path is a failure with the unmet precondition named. Do not mark it verified via a different headless path unless the feature lists that path as an accepted entry point.

## Feature entry contract

Each feature file: H1, one paragraph, then exactly these H2s in order:

1. `Sub-features`
2. `How to get to it (user POV)`
3. `Driving it with verify-iris`
4. `Gotchas`

## Features

- [Startup](./startup.md). MainWindow init smoke without a lasting window.
- [Companion tile](./companion-tile.md). IRIS IDE 80:20 tile contract.
- [Control HTTP](./control-http.md). `/v1/invoke` boundary without writing shared endpoints.
- [Chat stop](./chat-stop.md). Stop button / turn cancel contract.
- [File drop](./file-drop.md). IDE bundle markers and file-drop wiring.
- [No console](./no-console.md). Windows CREATE_NO_WINDOW / pythonw contracts.
