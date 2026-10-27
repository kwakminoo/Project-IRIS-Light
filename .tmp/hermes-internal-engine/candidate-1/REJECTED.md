# Rejected shapes

Judged on what the caller must learn, not on how little code the first patch would touch.

## Import AIAgent in the Qt process

Public API would be `AIAgent(...)` plus callbacks mapped onto worker signals. One process, no pipe.

The caller then owns Hermes init kwargs, session persistence, toolset lists, and every native import Hermes pulls. A Hermes exception shares the Qt fatal path. Restart is process restart. The IRIS venv is not CPython 3.14. `_gateway_child_env` exists because that mix already broke `pydantic_core`.

Depth is an illusion. The import is small. The leaked policy is the whole agent.

## Keep `:8642` and hide install

`ensure_hermes_gateway_running` already exists. Own the home directory, kill on close, stop telling the user to run `hermes gateway`.

Callers still construct `HermesClient(base_url, api_key=...)`. They still distinguish `/health`, `/v1/models`, and chat 401. They still pass `hermes_command`. The module they learn is the HTTP adapter plus the process manager. That is the current wide API with a friendlier README.

This candidate treats that as attach point (a) from HOW.md and refuses it as the default. External gateway stays a parsed `EngineSource` for people who already run Hermes. It is not the IRIS-only path.

## Swap only the child argv

Launch an IRIS-owned binary that still speaks OpenAI HTTP and MCP. Workers stay.

The public types remain URL, key, and SSE dicts. Every later change to readiness still edits `HermesClient` and `hermes_gateway.py` together. Information leakage. The user can still attach `:8642`. The done predicate fails.

## Third backend in MainWindow

Add `resolve_backend_route()` = engine next to hermes and ollama. New worker, new settings meaning.

Two send paths for the same tool turn. An agent copies whichever `_launch_chat_turn_bound` branch it opens first. `hermes_enabled` keeps meaning "gateway child exists." Rejected.

## In-process tools, drop MCP

Call `ActionRegistry.invoke` from the sidecar with a Python import.

The sidecar would load IRIS, Qt bindings, and Control Surface on the Hermes interpreter. BrowserSession and the HUD would share that process. The three-tool HTTP contract is the isolation that already works. Dropping it widens the public tool API and merges crash domains.

## Vendor Hermes into the repo

MIT allows it with notice. Callers would `from hermes...` or a subtree.

§3.4 is product policy, not a legal block. Vendoring puts Hermes on IRIS's interpreter and on every clone. The 3.14 pin and the Qt fatal wall come back. Isolation is the reason the sidecar exists. Vendoring fights that.

## Dual memory

Map IRIS `conversation_id` onto `AIAgent(session_id=...)` and also keep SQLite.

Two writers for one chat. Cancel, edit, and reload diverge. `StatelessTurn` exists so that state cannot be expressed. Hermes session DB is disabled in the sidecar.

## Per-turn sidecar spawn

Start `AIAgent` for each send, then exit. No warm process, no closeEvent kill.

The caller still calls `run_turn`. Hidden cost is install-scale startup on every message, plus MCP re-attach each time. One long-lived child is the ready state `ensure_ready` already names.

## New approval widget

A second confirm next to HUD `ask_human`.

Two ways to approve `project.run`. `hosts.py` already rejects `confirm_required` without HUD. The engine would grow an approval callback the chat worker does not want. Flag the three project actions. Stop.

## Gateway plus sidecar at once

Health worker starts `:8642`. Chat uses `AIAgent`. Or the reverse.

Two ready meanings. Two homes. Two ways to fail. `EngineSource` is one value. Default is sidecar only.

## Leave `HermesClient` as a public chat API

"Engine for lifecycle, client for tokens."

Callers coordinate two modules to complete one send. Pass-through plus leakage. `run_turn` yields `TurnEvent`. The HTTP client is `_compat.py`.
