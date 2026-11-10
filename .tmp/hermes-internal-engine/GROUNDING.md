# How grounding: IRIS ↔ Hermes (2026-10-27)

Original question: How does IRIS currently run Hermes Agent, and where would an in-process or IRIS-owned internal engine attach?

Explorers: gateway `3870225e`, chat `7ee0dd8a`, tools `812dae65`, upstream `c6c08315`.

## Gateway

IRIS already starts/stops/restarts a hidden child: `venv python -m hermes_cli.main gateway run --quiet --accept-hooks` on `127.0.0.1:8642`. Home is `%LOCALAPPDATA%\hermes`, not the repo. Source is cloned there, not vendored. Process outlives IRIS close. `LICENSE.md` §3.4 keeps Hermes unbundled on purpose. Windows: no `CREATE_NEW_PROCESS_GROUP`, no `--replace`. `/health` is unauthenticated alive; chat needs Bearer `API_SERVER_KEY` plus `/v1/models`.

## Chat

Send → `UserTurn` → `HermesChatWorker` POST SSE `/v1/chat/completions`. IRIS SQLite owns history and resends full `messages`. No Hermes session id. Cancel is a worker flag, not socket abort. Hermes-on never falls back to Ollama if gateway start fails. Worker exceptions stay off the Qt slot.

## Tools

Hermes sees three MCP tools: `iris_get_state`, `iris_get_catalog`, `iris_invoke`. Sync writes `config.yaml` and disables Hermes `terminal`/`browser` toolsets. Invoke is HTTP to Control Surface (`8765+`). Browser/YouTube/mini-player go through `BrowserSession`. File/terminal have no HUD; path jail + IDE terminal + disable Hermes terminal. In-process `AIAgent` would merge crash domains and freeze GUI on gateway restart.

## Upstream

MIT. Local checkout `0.21.5` at `%LOCALAPPDATA%\hermes\hermes-agent` (SHA `4787e4d`). Public API `from run_agent import AIAgent` exists inside the Hermes venv only. Core deps are pinned `python_version >= '3.14'` even though `requires-python` says `>=3.11,<3.15`. IRIS never imports `AIAgent`. Ollama is `provider: custom` + `:11434/v1`, not `ollama-cloud`.
