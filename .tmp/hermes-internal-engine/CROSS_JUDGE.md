# Arena cross-judge: hermes-internal-engine

Read: `.tmp/hermes-internal-engine/ARENA_RUBRIC.md`, `HOW.md`, and both candidate packages (`USAGE.md`, `DESIGN.md`, `RATIONALE.md`, `REJECTED.md`). Scale: 0 miss, 1 partial, 2 meet.

## Scores

| criterion | candidate-1 | candidate-2 | note |
|---|---|---|---|
| 1. IRIS-only launch reaches a ready agent; user never installs, starts, or attaches Hermes | 2 | 2 | Both default to an IRIS-owned child under `~/.iris-light/engine`. C1: `shared_engine().ensure_ready()` in `.tmp/hermes-internal-engine/candidate-1/USAGE.md`. C2: `shared_engine().ensure()` in `.tmp/hermes-internal-engine/candidate-2/USAGE.md`. Neither asks the user to run `hermes gateway` or point at `:8642`. |
| 2. Chat UI, BrowserSession, YouTube/mini-player, Control Surface, SQLite stay on current seams | 2 | 1 | C1 keeps the live tool hop: sidecar → iris-control MCP stdio → Control Surface HTTP (`candidate-1/DESIGN.md` data flow; `iris_control_stdio.py` unchanged). C2 keeps ChatPanel, `BrowserSession`, and SQLite, but the hosted product path drops MCP/HTTP and invokes `call_registered` over a pipe (`candidate-2/DESIGN.md` module map: `hermes_iris_control_sync.py` / `iris_control_stdio.py` “Compat only”). That is a new tool seam. |
| 3. Hermes agent loop reused, not rewritten | 2 | 2 | Both call `AIAgent.run_conversation` in the Hermes venv (`candidate-1/DESIGN.md` `_sidecar_main.py`; `candidate-2/DESIGN.md` `host_main.py`). C2 wraps tools as IPC callables around that loop; that is extra glue, not a rewritten conversation loop. |
| 4. Agent faults stay out of the Qt process (`0xC0000409` cannot come from the loop) | 2 | 2 | Both forbid `from run_agent import AIAgent` in the GUI interpreter (`candidate-1/DESIGN.md` invariants; `candidate-2/DESIGN.md` Qt and crash domain). Worker `try/except` + `failed.emit` stays. C2 still moves tool bodies into the Qt process (see Red flags); that is not the agent loop, so it does not drop this score. |
| 5. Public surface is small; callers do not coordinate install, port, key, and spawn | 2 | 1 | C1: one `Engine` with `ensure_ready` / `run_turn` / `shutdown`; `run_turn` calls `ensure_ready`; URL and key never appear at the worker (`candidate-1/USAGE.md` call sites 1–3; `parse_engine_source` in `candidate-1/DESIGN.md`). C2: chat worker calls `ensure()` then `handle.stream_turn(...)` (`candidate-2/USAGE.md`); `attach_compat(base_url=..., api_key=...)` is a public method that takes a port and key; `EnginePhase`, `IRIS_ENGINE_TOOLS`, and `display_host()` sit on the public surface (`candidate-2/DESIGN.md`). |
| 6. External Hermes is compatibility only; no second chat path | 2 | 1 | Both keep `HermesChatWorker` signals and refuse a third `BackendRoute` (`candidate-1/REJECTED.md` “Third backend”; `candidate-2/REJECTED.md` “New backend name”). C1 parses `ExternalGateway` from settings (`hermes_external_gateway`) so there is one ready call. C2 has two public ready entries (`ensure` → `READY`, `attach_compat` → `COMPAT`) and a public `EngineMode` (`candidate-2/DESIGN.md` Settings). Boot as written only calls `ensure()`, so compat settings have no owner unless some other caller invokes `attach_compat`. |

**Totals:** candidate-1 **12 / 12**. candidate-2 **9 / 12**.

## Base recommendation

**Use candidate-1 as the base.**

It is the same product decision as candidate-2 (IRIS-owned Hermes-venv child, no default `:8642`, no in-process `AIAgent`, kill on close, HUD flags on file/terminal work) with a tighter attach: one handle, one ready call, settings-parsed compat, and the tool plane IRIS already has. `.tmp/hermes-internal-engine/HOW.md` attach point (a) plus a swapped child argv that speaks a private pipe instead of OpenAI HTTP — not attach point (b). That matches the crash, interpreter, and license walls in HOW.md without inventing a second invoke path.

Candidate-2 is the same architecture with more ceremony and one structural mistake: hosted tools leave MCP/Control Surface HTTP. That is two ways to run `iris_invoke` (pipe + `call_registered` vs MCP + HTTP). Keep C1’s three-process tool path.

## Grafts

Take these from candidate-2. Do not take its hosted tool transport.

1. **Import linter, not a comment.** `candidate-2/DESIGN.md` “Qt and crash domain”: reject `run_agent`, `hermes_cli`, and the sidecar entry from `iris.ui` and from anything `MainWindow` imports. C1 only states the invariant.

2. **Two interpreter NewTypes plus a child self-check.** Graft `EnginePython` / `GuiPython` and `host_main`’s “refuse to start if this interpreter is the IRIS GUI venv” (`candidate-2/DESIGN.md`). C1’s `_sidecar_main.py` says “No iris imports” but does not fail closed on `sys.executable`.

3. **`HermesHome` vs `EngineHome`.** C2’s distinct NewTypes stop compat from writing `~/.iris-light/engine` (`candidate-2/DESIGN.md` Domain types). C1 only has `EngineHome`.

4. **Boot assert on dangerous actions.** Graft `assert_dangerous_actions_confirm` and consider adding `project.create_scaffold` to C1’s three flag flips (`candidate-2/DESIGN.md` Approval; `candidate-1/DESIGN.md` Approval). One list, fail at startup, not on the first write.

5. **One tool-name tuple, checked at boot.** Graft `IRIS_ENGINE_TOOLS` as a private/constant check against the iris-control catalog (`candidate-2/DESIGN.md`). Keep it off `__all__`. C1’s “disabled toolsets come from `config.yaml` only” is right; the boot compare is the missing lock.

6. **Reserve stdout before `import run_agent`.** C2’s open risk is real for both pipes (`candidate-2/RATIONALE.md` Open questions). Logging to the protocol stream becomes `PROTOCOL` on the first line. Redirect stderr/log file first. C1’s `parse_turn_event` does not name this.

7. **Reconcile `ensure_ready` from disk and pid, not only `_child.alive()`.** C2’s supervisor text (`candidate-2/DESIGN.md` Supervisor and handle). C1’s in-memory `_child` misses a dead process whose handle was not cleared.

8. **One mode at a time, stated as an invariant.** Graft “hosted shut down before compat returns” (`candidate-2/DESIGN.md` `attach_compat`). C1 fixes source at `shared_engine()` first parse; say what happens if settings flip, and do not run both children.

Do **not** graft: `attach_compat(base_url, api_key)` as a caller API; public `EnginePhase` with `INSTALLING`/`STARTING`; `ModelRef` beside `HermesInferenceTarget`; `stream_turn(attempt: object)`; pipe `tool_call` / in-process `call_registered` as the default tool path; minted `EngineHandle` (C1’s single `Engine` is enough).

## Red flags

Flagged against the named failure modes.

### Candidate-1 (base)

- **Leakage (mild).** `EngineErrorCode` includes `AUTH` on a path that no longer binds an API server (`candidate-1/DESIGN.md` Public types). Fine for `_compat.py`; do not let the default sidecar emit `AUTH`.
- **Pass-through (mild).** `HermesChatWorker` still maps every `TurnEvent` to Qt signals (`candidate-1/USAGE.md` call site 2). Acceptable adapter. Do not also keep `HermesClient` arguments on that worker.
- **Global writer.** `apply_engine_home` mutates what `hermes_home()` and `sync_iris_control` read (`candidate-1/DESIGN.md` `_home.py`). One writer is correct; a process-global `HERMES_HOME` is still a shared mutable. Compat must not call it.
- **Missing structural guard.** Crash-domain rule is prose only (`candidate-1/DESIGN.md` Invariants). Without C2’s linter, the next patch can `import run_agent` in a worker.

No shallow module, no two chat paths, no split tool ownership, no public temporal stages. `ensure_ready` hides install/start (`candidate-1/DESIGN.md` Lifecycle). `REJECTED.md` already throws out the shallow `:8642` module, in-process `AIAgent`, dual memory, and a second approval widget.

### Candidate-2 (loser)

- **Two ways + split ownership.** Hosted tools are pipe → `call_registered`; compat tools are MCP → Control Surface HTTP (`candidate-2/DESIGN.md` Hosted process / Compat adapter). Two invoke paths for the same catalog. C2 `REJECTED.md` correctly rejects “a second in-process registry on the host,” then builds a second transport to the *same* registry.
- **Leakage.** Public `EnginePhase` (`INSTALLING`, `STARTING`, `STOPPING`), public `IRIS_ENGINE_TOOLS`, `display_host()`, `attach_compat(base_url, api_key)` (`candidate-2/DESIGN.md`, `candidate-2/USAGE.md`). Callers can see stages, tool names, and a URL again.
- **Temporal decomposition.** Chat site is `ensure()` then `stream_turn()` (`candidate-2/USAGE.md` call site 2). C2 `REJECTED.md` rejects a public `install/start/wait_hello/stream/stop` sequence, then splits ready and send at the caller. C1 collapsed that.
- **Pass-through.** `stream_turn(self, attempt: object, *, should_cancel=...)` (`candidate-2/DESIGN.md`). `ChatAttempt` leaks through the boundary. C1’s `StatelessTurn` + `ChatTranscript.parse` is the actual parse.
- **Two model types.** `ModelRef` (`candidate-2/DESIGN.md`) vs existing `HermesInferenceTarget` (C1 reuses it on purpose, `candidate-1/DESIGN.md` “Do not add a parallel InferenceTarget”).
- **Shallow compat module.** `attach_compat` is the current HTTP client with a new name: URL, key, and `ensure_hermes_gateway_running` inside (`candidate-2/DESIGN.md` Compat adapter). Allowed as private `_compat.py`; not as a public supervisor method.
- **Unused type.** `ConversationId` is defined and “never passed” (`candidate-2/DESIGN.md`). Dead domain type next to the real SQLite id.

## Risks the implementer must not ignore

These are in HOW.md and both open-question lists. A C1 implementation that skips them will fail in the same places the current gateway already failed.

1. **`AIAgent.run_conversation(..., conversation_history=)` vs IRIS `history_dicts`.** C1 `RATIONALE.md` asks whether `system` rows survive. HOW.md builds a large instruction block and POSTs full `messages`. If the loop rejects or drops `system`, do not invent a second prompt builder in the worker — fold at `ChatTranscript.split_for_agent` only, and test against a real `history_dicts` row first (C1’s own next step).

2. **Session persistence must be off in the child, and proven.** `session_db=None`, `skip_memory=True`, `_persist_disabled=True` (C1) / `session_id=None`, persist-off (C2) are wishes until someone checks the checkout at SHA `4787e4d`. A Hermes SQLite row under `EngineHome` or `%LOCALAPPDATA%\hermes` is dual memory. C1 `REJECTED.md` “Dual memory.”

3. **Cancel does not abort Control Surface work.** HOW.md: cancel is a flag; `status=timeout` does not cancel queued UI work. `hard_interrupt` may stop the next model call only. Do not add a second cancellation plane. Do not tell the UI the tool stopped.

4. **Existing `%LOCALAPPDATA%\hermes` is not `EngineHome`.** Both candidates clone fresh into `~/.iris-light/engine` and ignore the working tree unless compat is on. First-run must not silently rewrite the user CLI home, and must not read it as the product path. Windows home is `%LOCALAPPDATA%\hermes`, not `~\.hermes` (HOW.md Gotchas).

5. **Official `install.ps1` writes the wrong story.** Both leave “ps1 first, then clone bypass” open. `hermes_install.py` today targets the user Hermes tree. Internal home should use the clone bypass (and a pin) or the official script will install into the old home. HOW.md: official installer is flaky on current Windows.

6. **Pin a SHA; name who bumps it.** Local tree is `0.21.5+dirty`. `EngineHome` without a pin is “whatever clone finished.” Dirty local patches (`apply_ollama_options_guard`) will not appear in a clean clone.

7. **Env and spawn flags are solved incidents.** Strip `VIRTUAL_ENV` / `PYTHONPATH` / uv / conda. `CREATE_NO_WINDOW` only. No `CREATE_NEW_PROCESS_GROUP`. No `--replace`. HOW.md Gotchas. Reuse `_gateway_child_env`, do not rewrite it from memory.

8. **Probe `EnginePython` before spawn.** Import `hermes_cli, aiohttp, mcp, ruamel.yaml, dotenv` in that interpreter. A 3.11 tree that “installed” is `WRONG_PYTHON` / `PYTHON_RANGE`, not a later sidecar crash (HOW.md; both designs). IRIS `.venv` is not that interpreter.

9. **Stdout is the protocol.** Any Hermes log line before redirect is `PROTOCOL` forever. Configure logging to `~/.iris-light/engine/logs/` first. The child must not import the `iris` package; spawn `_sidecar_main.py` as a file path on `EnginePython`.

10. **One lock, one child.** Health worker, chat worker, and `closeEvent` share `Engine._child`. Callers do not spawn. `run_turn` may call `ensure_ready`; that must take the same lock or two sidecars appear.

11. **Close order.** `stop_control_surface` then `shutdown()` (`candidate-1/USAGE.md` call site 3). `shutdown` must not raise. External/compat must not be killed. Default sidecar must die so nothing keeps `:8642` and MCP does not say “Start Iris Light first” (HOW.md).

12. **Delete the old default callers in the same change.** Health, chat, and `SetupProtocol` stop calling `ensure_hermes_gateway_running` / constructing `HermesClient(base_url, api_key=...)` together (`candidate-1/DESIGN.md` Module map; C1 `RATIONALE.md` `migrate-callers-then-delete-legacy-apis`). Leaving both is two ready meanings.

13. **No Ollama worker fallback.** Sidecar failure is `TurnFailed` / a chat error card. `_hermes_fallback_attempts` stays model rotation through the same engine (HOW.md; both USAGE files).

14. **LICENSE.md §3.4.** Still unbundled. Clone + MIT notice under the IRIS data dir. Relationship line changes from HTTP/`:8642` to sidecar/IPC. Do not vendor into `iris/`.

15. **Do not graft C2’s tool hop onto C1.** In-process `call_registered` from `HermesChatWorker` can deadlock `ask_human` (worker waits on UI, UI waits on worker) or skip `runs_off_ui_thread`. That is a new `0xC0000409` / freeze path even though the agent loop stays out of Qt. Keep MCP → Control Surface HTTP on the default path.
