# Rejected shapes

This page is the shapes this candidate threw out while forming the hosted pipe. It is not a review of the other arena runners.

## Public OpenAI gateway as the product API

IRIS already has `HermesClient`, `/health`, `/v1/models`, and Bearer keys. The smallest diff is to pin the clone, move home, and stop the child on quit.

Callers still pass a URL and a key. Ready still has four answers (alive, key, models, chat). MCP stdio stays a third process. A user can still attach `:8642`. The public API exposes transport. Changing the listen port or the SSE event names touches the worker, settings, and health probe together.

Rejected. The product ask is that a user never connects. An auto-started server is still a server. Interface depth is a URL plus a process manager, which is what IRIS already has.

## `AIAgent` in the Qt process

`from run_agent import AIAgent` is the upstream public API. One in-process call would hide install, HTTP, and MCP. The worker would map callbacks to the same signals.

The GUI interpreter would have to satisfy Hermes 3.14 pins or the import would fail the way `VIRTUAL_ENV` already failed (`pydantic_core`). A native fault or an uncaught exception next to a Qt slot is `0xC0000409`. `restart_hermes_gateway` becomes "reload in the GUI" or "restart IRIS." Session persistence on `AIAgent` forks history unless every caller remembers to disable it.

Rejected. The small public API leaks the crash domain and the interpreter. Isolation is the point of a handle.

## Vendor Hermes into `iris/`

A subtree in the repo would hide clone and SHA from `ensure`. MIT allows it with notice.

Every IRIS contributor would carry Hermes history and 3.14 deps next to PyQt. `LICENSE.md` §3.4 would be a lie until rewritten. An agent fixing chat would have two trees to edit.

Rejected while policy is unbundled. Vendoring reduces install steps and increases what every IRIS file-adjacent edit can break.

## New backend name beside hermes and ollama

`resolve_backend_route` could grow `backend="engine"`. A new worker could sit next to `HermesChatWorker`.

`MainWindow` would have two tool-capable chat paths. `hermes_enabled`, `hermes_owns_local_intents`, and settings ping would keep meaning "the :8642 child." An agent copies the first branch it finds.

Rejected. Two ways to send a tool turn. Compat is a handle implementation, not a second `BackendRoute`.

## Hosted host that still listens on `:8642`

Spawn `hermes_cli.main gateway run` from `EngineHome`, keep `HermesClient`, delete MCP later.

Chat workers would keep coordinating URL, key, and ready probes. The "internal engine" would still be a public HTTP server on the port the user already knows. Compat and hosted would be the same transport with different homes, so every probe stays on the public API.

Rejected. A hidden gateway on the same protocol is temporal reuse of a server IRIS is trying to stop being. The pipe is the hosted transport. HTTP stays compat.

## Tools as a second in-process registry on the host

Pass IRIS actions into `AIAgent` as native tools and skip `iris_invoke`.

The host would need a copy of the catalog, risk flags, and browser policy. `ActionRegistry` would no longer be the one invoke. YouTube and the mini-player would grow a second entry or they would vanish from the host.

Rejected. Split ownership of tools. `call_registered` is the one invoke. The host registers the names IRIS sends in hello.

## Stdin/stdout replaced by a supervisor that chat calls in stages

`install()`, `start()`, `wait_hello()`, `stream()`, `stop()` as public methods.

Callers would coordinate a sequence. A health worker that forgets `wait_hello` would look connected. That repeats the `/health` vs `/v1/models` split.

Rejected. Shallow API. `ensure` hides the stages. Phase lives in the supervisor.

## Keep the gateway alive across IRIS quit

A warm host on next launch avoids spawn cost.

After quit, Control Surface is down. MCP or a leftover HTTP client fails with "Start Iris Light first." The next launch must probe a zombie. `closeEvent` already stops Control Surface. A live agent without IRIS is not a product state.

Rejected. Warm start is a hidden second lifecycle. `shutdown` on close is the one lifecycle.

## Hermes session id mapped to IRIS `conversation_id`

`AIAgent(session_id=str(conversation_id))` would let Hermes own memory.

IRIS already resends `history_dicts`. Two stores would disagree after an edit, a delete, or a failed turn. Cancel and fallback would write rows the UI never shows.

Rejected. `_TurnRequest` has no session field so the second store cannot be used by accident.
