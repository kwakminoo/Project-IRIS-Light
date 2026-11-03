# Control HTTP

Control HTTP proves the local `/v1/invoke` and `/v1/state` contract (auth, success, failure, timeout shapes) without writing the shared `~/.iris-light` control endpoint files.

## Sub-features

- `invoke-ping` returns success for a registered action.
- `invoke-errors` return structured failures for bad JSON and missing actions.
- `ui-timeout` surfaces timeout status without claiming cancel.

## How to get to it (user POV)

- With Iris running, Hermes MCP or other clients call `http://127.0.0.1:<port>/v1/invoke` using the bearer token from `~/.iris-light/control_token`.

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.
- Do not require a live Iris window. This feature binds a temp port.

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature control-http`
- **Observe.** Exit code `0`. Evidence `report.json` `"ok": true`.
- **Live smoke (optional).** With Iris up: `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\invoke.py ping` and expect `"ok": true`.

## Gotchas

- The contract check stubs `write_control_endpoint` so it will not clobber the user’s live port files. Do not remove that stub when editing the check.
- Live `invoke.py` against a foreign Iris can affect the user’s session. Prefer headless prove for routine changes.
- `status=timeout` does not guarantee the UI work was cancelled.
