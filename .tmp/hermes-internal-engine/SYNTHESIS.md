# Synthesized design

Base: candidate-1 (parent 11/12, cross-judge 12/12). [교차 채점](61a9a5d2-e459-4178-8f26-5bfc4b273f73) agreed. Both runners rejected in-process `AIAgent` and a polished `:8642` default.

## Product

IRIS owns a Hermes-venv sidecar that runs `AIAgent.run_conversation`. Qt never imports Hermes. The default path does not bind `:8642`. Chat stays `HermesChatWorker` signals. Tools stay three MCP names into Control Surface HTTP. History stays IRIS SQLite. Close kills the sidecar. External Hermes is a settings-parsed `ExternalGateway`, not a second send path.

## Public surface

`shared_engine().ensure_ready()` / `run_turn(StatelessTurn)` / `shutdown()`. `run_turn` calls `ensure_ready`. Callers do not pass URL, key, or command.

## Grafts from candidate-2

- Import linter: no `run_agent` / `hermes_cli` / sidecar entry from `iris.ui`
- `EnginePython` / `GuiPython`; child exits if it is the GUI interpreter
- `HermesHome` vs `EngineHome`
- `DANGEROUS_ACTIONS` boot assert; flags on write/run/rename/create_scaffold
- Private `IRIS_ENGINE_TOOLS` catalog check
- Redirect logs before `import run_agent`
- `ensure_ready` reconciles from disk and pid
- One mode at a time; settings flip shuts the other child

## Rejected grafts

`attach_compat(url, key)`, public `EnginePhase`, `ModelRef`, `stream_turn(ChatAttempt)`, pipe `tool_call` → `call_registered`.

## First unit

`iris/engine/types.py` plus a test that `ChatTranscript.parse` accepts a real send payload (system + history_dicts + trailing user) and `split_for_agent` rejects a transcript that does not end on a user message.
