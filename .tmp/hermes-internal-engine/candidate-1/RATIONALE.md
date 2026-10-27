# Why the sidecar engine

## Problem

IRIS already starts a hidden Hermes child and chats with it over OpenAI HTTP on `127.0.0.1:8642`. The user still has a separate install tree, a port, an API key, and a process that outlives the app. The request is IRIS-only launch, agent ready, chat and tools, no manual `hermes gateway`, no attached `:8642`. Existing ChatPanel, BrowserSession, YouTube, mini-player, Ollama providers, Control Surface, and SQLite history must stay. Hermes errors must not become Qt `0xC0000409`. File and terminal work need a real HUD confirm. LICENSE.md §3.4 keeps Hermes unbundled. Upstream is MIT at `%LOCALAPPDATA%\hermes\hermes-agent` (`AIAgent` in `run_agent.py`). Core deps want CPython 3.14. The IRIS venv is a different interpreter. `HermesChatWorker` already keeps exceptions inside `run()`. Tools are three MCP names into Control Surface HTTP. `project.write_file` and `project.run` are `risk="medium"` and skip confirm today.

## Usage (caller's view)

Specified in `USAGE.md`. Three imports from `iris.engine`, three call sites.

`HermesHealthWorker.run` calls `shared_engine().ensure_ready()` and keeps its Qt signals.

`HermesChatWorker.run` builds a `StatelessTurn` from the SQLite transcript and iterates `run_turn`. It drops `base_url`, `api_key`, and `command`. Signals stay so `_launch_chat_turn_bound` does not grow.

`MainWindow.closeEvent` calls `shutdown()` after `stop_control_surface`.

Approval is a flag on the existing registry, not an engine method.

## Shape

The public API is one `Engine` with `ensure_ready`, `run_turn`, and `shutdown`. Complexity that used to leak as ports, keys, health-versus-models, `HERMES_HOME`, and `hermes gateway run` sits behind those three calls. Callers do not coordinate install then start then chat. `run_turn` calls `ensure_ready`. Per interface depth, and per `minimize-reader-load`.

Data structures first, per `foundational-thinking` and `model-the-domain`. `EngineSource` is a union. `InternalSidecar` always kills on close. `ExternalGateway` never does. A boolean `kill_on_shutdown` the caller could flip is an illegal state, per `type-system-discipline`. `StatelessTurn` has a `ChatTranscript` and no session id, so a later author cannot "just add" Hermes memory on the IRIS type. `TurnEvent` is a closed union. OpenAI SSE dicts and NDJSON stay in private parsers, per `boundary-discipline`.

The default child is a Hermes-venv process that imports `AIAgent` and calls `run_conversation(user_message, conversation_history=...)`. That is the upstream loop, measured in `agent/conversation_loop.py`. IRIS does not rewrite it. The Qt process does not import it. That split is the crash and interpreter wall. Env stripping reuses `_gateway_child_env`. `CREATE_NEW_PROCESS_GROUP` stays forbidden.

Home is `~/.iris-light/engine`. `%LOCALAPPDATA%\hermes` is not the default tree. `apply_engine_home` is the single writer `hermes_home()` and `sync_iris_control` read, per `encode-lessons-in-structure`. Disabled toolsets stay the one `config.yaml` list sync already writes. The sidecar does not pass a second list.

`ensure_ready` and `shutdown` are reconciliation steps, per `make-operations-idempotent`. Ready plus ready does not spawn. Stopped plus shutdown does not kill twice. A dead child is `Failed`. The next `ensure_ready` respawns.

The sidecar process is the one write target shared by health, chat, and close. The lock lives on `Engine`. Callers do not share a file, per `separate-before-serializing-shared-state`. SQLite remains MainWindow's store. The sidecar sets `session_db=None` and `_persist_disabled=True`.

This is a redesign of the attach point as if "IRIS owns the engine" had been day one, per `redesign-from-first-principles`. It is not a new flag on `ensure_hermes_gateway_running`. Health, chat, and SetupProtocol move to `Engine` in one wave, per `migrate-callers-then-delete-legacy-apis`. `HermesClient` remains only inside `_compat.py`.

Approval stays on `ActionRegistry`. The engine never sees HUD. That keeps the public API small, per `laziness-protocol`. The user still gets a real confirm, per `experience-first`.

Source stays unbundled. MIT notice travels with the checkout under the IRIS data dir. LICENSE.md §3.4 text changes the relationship line and does not start vendoring.

## Synthesis decision

filled by arena

## Tradeoffs accepted

- We accept a cold sidecar after every IRIS close in exchange for no orphan `:8642` and no "Start Iris Light first" MCP zombie on a leftover gateway.
- We accept a private NDJSON pipe in exchange for never binding an OpenAI server the user can attach. The agent loop is still Hermes. The pipe is a parser, not a second loop.
- We accept first-send latency when boot health has not finished in exchange for one ready path. Chat does not depend on the health worker succeeding first.
- We accept that in-flight `project.run` still continues after UI cancel in exchange for not inventing Control Surface cancellation. Timeout already documents that gap.
- We accept a settings field `hermes_external_gateway` (default false) in exchange for one chat API. External Hermes is a parsed `EngineSource`, not a second worker.
- We accept clone-into-`~/.iris-light/engine` instead of a git submodule in exchange for keeping §3.4 isolation and the 3.14 venv off the IRIS interpreter.
- We accept that `_sidecar_main.py` cannot import `iris` in exchange for a hard process boundary. Shared types are dumped as JSON at the pipe, then parsed again.

## Alternatives considered

- **In-process `from run_agent import AIAgent`.** Smallest call chain, and it matches the "prefer module calls" wish. It exposes the 3.14 venv, IRIS `VIRTUAL_ENV` pollution, and Qt `qFatal` to every Hermes exception. Restart becomes restart IRIS. Interface looks one import deep and leaks the whole crash domain. Rejected on boundary and crash ownership.
- **Keep the OpenAI gateway as the default, own only install and home.** Smallest diff. Callers still learn `/health` versus `/v1/models` versus chat 401, `API_SERVER_KEY`, and `hermes gateway stop --all`. The public API stays the current wide HTTP client. That is a shallow module. Rejected on interface depth.
- **New chat backend name beside hermes and ollama.** `_launch_chat_turn_bound` grows a third worker. Settings that mean `hermes_enabled` keep meaning "the :8642 child exists." Two ways to send a tool turn. Rejected per two-ways and per `laziness-protocol`.

## Open questions and risks

- Does `AIAgent.run_conversation` plus `conversation_history` accept IRIS `system` rows the way `/v1/chat/completions` does, or do we have to fold the instruction block into the first user message?
- Does `hard_interrupt` stop an `iris_invoke` that Control Surface has already started, or only the next model call?
- Official `install.ps1` still runs first in `hermes_install.py`. Should internal home skip it and use only the clone bypass, given HOW.md notes it is flaky on current Windows?
- Local checkout is `0.21.5+dirty` at SHA `4787e4d`. Which SHA does `EngineHome` pin, and who bumps it?
- Users with a working `%LOCALAPPDATA%\hermes` tree will not be migrated unless we copy or ask. Is first-run allowed to clone fresh into `~/.iris-light/engine` and ignore the old tree unless `hermes_external_gateway` is on?

## Next implementation step

Write `iris/engine/types.py` and a failing test that `ChatTranscript.parse` plus `split_for_agent` accept a real `history_dicts` row and reject a transcript that does not end on a user message.
