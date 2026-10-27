# Why a hosted AIAgent pipe

## Problem

IRIS already starts Hermes as a hidden OpenAI server on `127.0.0.1:8642` and chats over SSE. Tools bounce through a third MCP process back into Control Surface HTTP. The user still has a gateway to install, a port to treat as "connected," and a child that outlives quit. The product ask is IRIS-only launch to a ready agent, with the existing chat UI, `BrowserSession`, Ollama providers, Control Surface tools, and SQLite history left in place. Hermes must keep its own agent loop. The GUI `.venv` is not CPython 3.14. A Hermes exception in a Qt slot is `0xC0000409`. `LICENSE.md` §3.4 keeps the Hermes tree out of the repo. File and terminal actions today have path jail and a disabled Hermes terminal, but they do not go through `ask_human`.

The current seams make three attach points look available. Keep the HTTP child and polish lifecycle. Import `AIAgent` in the GUI process. Or treat Hermes as a worker IRIS hosts. Those are different products. This sketch takes the third.

## Usage (caller's view)

The next engineer imports `shared_engine` and calls `ensure`, `stream_turn`, and `shutdown`. Boot (`HermesHealthWorker.run`) becomes `ensure()`. A chat turn (`HermesChatWorker.run`) keeps the `ChatAttempt` fallback loop and iterates `TurnEvent` from `stream_turn(attempt)`. Quit (`MainWindow.closeEvent`) calls `shutdown()` next to `stop_control_surface`. Compat is `attach_compat` on that same handle. The caller does not pass a port, a key, or a spawn command. See `USAGE.md` for the three sites written out.

## Shape

The domain object is an engine with one phase, not a URL the app connects to. `EnginePhase` is a state machine. `READY` and `COMPAT` cannot be true together. `EngineHandle` is a minted capability that can stream and cannot spawn. `_TurnRequest` has messages and a model, and has no session id, so Hermes SQLite cannot become a second history. `EngineHome` and `HermesHome` are different NewTypes. `EnginePython` cannot be the GUI interpreter. Failures are a closed `EngineFailureCode` union. Validation of worker dicts, SSE, and host lines happens at those boundaries. Inside the engine package the types are trusted. Per `boundary-discipline` and `type-system-discipline`.

The hosted host imports `AIAgent` in the Hermes 3.14 venv and speaks framed JSON on stdin and stdout. There is no listening socket in the product path. The user cannot attach to a port because there is not one. Hermes `terminal` and `browser` stay disabled. The three IRIS tools are Python callables on the host that send `tool_call` lines. IRIS runs `call_registered`, the same function Control Surface HTTP already uses. MCP stdio exists only in compat. Per `redesign-from-first-principles` and `experience-first`. The user launches IRIS and talks. They do not run `hermes gateway`.

`DANGEROUS_ACTIONS` is the one list that forces `confirm_required` on file and terminal work. `ActionRegistry.ask_human` is the HUD. A boot assert fails if the registry drifts. `IRIS_ENGINE_TOOLS` is the one tool-name list. IRIS sends it in hello. The host does not hardcode names. Compat stdio is asserted against the same tuple. Per `encode-lessons-in-structure` and `model-the-domain`.

`EngineSupervisor` is the only writer of the child and the pipe. Health and chat workers ask it. They do not open their own Popen. The lock exists because one child is a real shared writer, not because two workers each keep a pid. Per `separate-before-serializing-shared-state`. `ensure` and `shutdown` reconcile from disk and pid facts. A second call or a crash mid-install converges. Per `make-operations-idempotent`.

The public API is three methods and the event types. Install, Python range, `AIAgent`, pipe framing, MCP, keys, and `:8642` stay in `_hosted` or `_compat`. The chat worker does not coordinate those steps. Call chain for a turn is three files. Per `laziness-protocol` and `minimize-reader-load`. After the migrate, chat and health workers stop calling `ensure_hermes_gateway_running` in the same change. Per `migrate-callers-then-delete-legacy-apis` and `outcome-oriented-execution`.

Qt never imports `run_agent`. Worker `try/except` stays. A host death is `HOST_EXIT`, not a slot exception. Aloha already uses a side process next to Qt for the same crash and license reason (`LICENSE.md` §3.3).

What the design does not do. It does not vendor Hermes into `iris/`. It does not keep `:8642` as the default ready check. It does not add a second chat backend name beside hermes. It does not rewrite `MainWindow` turn dispatch, `ChatPanel`, or `BrowserSession`.

## Synthesis decision

Filled by arena.

## Tradeoffs accepted

- We accept a cold host start on every IRIS launch in exchange for a child that cannot outlive quit and serve a dead Control Surface.
- We accept a private stdin/stdout protocol in exchange for deleting the user's ability to attach `:8642` in the product path. Compat keeps HTTP.
- We accept a Hermes venv next to the GUI venv in exchange for never importing 3.14-pinned deps into PyQt.
- We accept HUD prompts on `project.write_file` and `project.run` in exchange for a real approval path. Path jail alone is not approval.
- We accept MCP and `config.yaml` remaining on the compat path in exchange for not rewriting a user's existing gateway.
- We accept in-flight `project.run` surviving cancel in exchange for not changing the Control Surface timeout contract in this work.
- We accept keeping the `hermes_enabled` flag name in exchange for leaving `_use_hermes_backend` and `hermes_owns_local_intents` unrewritten.

## Alternatives considered

- Keep the `:8642` child and own only install and close. Callers still learn health vs ready vs key vs chat. MCP stays a third process. The public API stays a URL. Interface depth is low. Rejected because the product ask is "never connect," not "connect automatically."
- Import `AIAgent` in the GUI process. The public API would be even smaller, one in-process call. It exposes the Qt crash domain and the 3.14 vs `.venv` conflict to every turn. Rejected because `0xC0000409` is a hard constraint and env pollution is a solved incident that this would reopen.
- Vendor the Hermes tree into the repo. Callers would not wait on a clone. It hides install and breaks `LICENSE.md` §3.4 on purpose. Rejected while the policy is unbundled. MIT notice is not the block. Isolation is.

## Open questions and risks

- Does this tree's `AIAgent` accept `session_id=None` and persist-off without writing `~/.hermes` or `EngineHome` session rows?
- Does `AIAgent` expose an interrupt that aborts a turn between tokens, or only between tool calls?
- If Hermes logs to stdout before `host_main` redirects logging, the first protocol line is trash. Can the host import `run_agent` with stdout already reserved?
- Should first-run keep official `install.ps1` as a fallback into `EngineHome`, or only the clone bypass `hermes_install.py` already has?
- When a user has a working `%LOCALAPPDATA%\hermes` tree, does first hosted launch clone again into `EngineHome`, or offer compat attach? The default in this sketch is clone again so the product path never reads the user CLI home.

## Next implementation step

Write `host_main.py` so `EnginePython` imports `AIAgent`, answers one `hello`/`turn`/`delta`/`done` on pipes, and refuses to start under `GuiPython`, then drive that child from a QThread that never imports Hermes.
