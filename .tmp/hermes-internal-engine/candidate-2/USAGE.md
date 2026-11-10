# Use the hosted engine

IRIS starts an agent the way it starts Control Surface. The user launches IRIS. The agent is ready. There is no `hermes gateway` step, no `:8642` field to attach, and no Hermes install the user runs.

You import one object. You call `ensure`, then `stream_turn`, then `shutdown`. Install, the Hermes 3.14 venv, `AIAgent`, the pipe, MCP, and the old gateway live behind that object.

Hosted mode is the product. An external Hermes gateway is the same object in compatibility mode. Chat still goes through `HermesChatWorker` signals. Tools still go through `ActionRegistry`. History still lives in IRIS SQLite.

## What you import

```python
from iris.engine import shared_engine, EngineFailure, ContentDelta, ToolProgress, TurnDone, TurnFailed
```

`shared_engine()` returns the process-wide `EngineSupervisor`. Chat and health workers import only these names. `IRIS_ENGINE_TOOLS` is for the stdio boot assert.

## Call site 1. Boot (today `HermesHealthWorker.run`)

Replace gateway start, MCP sync, and `hermes mcp test` with one call. Keep the QThread. Do not run this on the Qt slot.

```python
# iris/ui/workers/hermes_workers.py  (HermesHealthWorker.run)

def run(self) -> None:
    try:
        handle = shared_engine().ensure()
        if isinstance(handle, EngineFailure):
            self.failed.emit(handle.user_message())
            return
        self.finished_ok.emit(True)
    except Exception as exc:
        self.failed.emit(str(exc) or type(exc).__name__)
```

`ensure()` is idempotent. A second call while the host is ready returns the same handle and does not spawn. A half-finished install resumes from the staging tree and rename-swaps, the way `hermes_install.py` already does.

The user-visible result is a ready indicator that means "a turn will stream." It does not mean `/health` on a port.

## Call site 2. Chat turn (today `HermesChatWorker.run`)

Keep the worker constructor, the Qt signals, the cancel flag, and the existing `ChatAttempt` fallback loop. Change only the inner stream so it talks to the handle, not `HermesClient`. One `stream_turn` is one attempt.

```python
# iris/ui/workers/hermes_workers.py  (HermesChatWorker.run, inner attempt)

handle = shared_engine().ensure()
if isinstance(handle, EngineFailure):
    self.failed.emit(handle.user_message())
    return

for index, attempt in enumerate(self._attempts):
    if self._cancel:
        break
    self.connecting.emit(attempt.model, handle.display_host())
    content_parts: list[str] = []
    try:
        for event in handle.stream_turn(attempt, should_cancel=lambda: self._cancel):
            if isinstance(event, ToolProgress):
                self.tool_progress.emit(event.line)
            elif isinstance(event, ContentDelta):
                content_parts.append(event.text)
                self.content_chunk.emit(event.text)
            elif isinstance(event, TurnDone):
                self.finished_ok.emit("".join(content_parts))
                return
            elif isinstance(event, TurnFailed):
                last_error = event.user_message()
                break
    except Exception as exc:
        last_error = str(exc) or type(exc).__name__
    # existing decide_fallback + switched.emit stay here
```

`MainWindow._launch_chat_turn_bound` stays. It still builds `messages` from `history_dicts` and still starts `HermesChatWorker`. It does not learn about pipes, `AIAgent`, or a URL.

A turn sends the full SQLite transcript. The host does not get an IRIS `conversation_id` and does not open a Hermes session row.

## Call site 3. Close (today `MainWindow.closeEvent`)

Control Surface already stops here. The hosted host must stop here too. The current gateway outlives IRIS. That is the bug this call site removes.

```python
# iris/ui/window/main_window.py  (closeEvent, next to stop_control_surface)

stop_control_surface(self)
shared_engine().shutdown()
```

`shutdown()` is idempotent. A second close, or a close when the host never started, is a no-op. After shutdown, `ensure()` on the next launch starts a new host.

## Compatibility mode

A user who already runs Hermes themselves, or a repair path that must attach a live `:8642`, uses the same handle.

```python
handle = shared_engine().attach_compat(
    base_url=settings.hermes_base_url,
    api_key=settings.hermes_api_key,
)
```

`HermesChatWorker.run` does not change for this case. `stream_turn` is still the iterator. Compat is an implementation of the handle, not a second branch in `MainWindow` or `_use_hermes_backend`.

Settings keep `hermes_enabled=True` as "the engine path is on." `settings.set` still refuses to turn that off. `hermes_base_url` is read only after `attach_compat`. Hosted mode ignores it.

## What the user does

1. Start IRIS.
2. Type in the existing composer.
3. Approve a file write or a `project.run` in the existing HUD when the catalog marks that action `confirm_required`.
4. Quit IRIS. The host dies with the app.

Browser, YouTube, and the mini-player stay on `BrowserSession` through `iris_invoke` → `ActionRegistry`. The Hermes `browser` and `terminal` toolsets stay off.

## What you do not do

- Do not import `run_agent` or `AIAgent` from the IRIS `.venv`.
- Do not call `ensure_hermes_gateway_running` from a chat or health worker after the migrate. That function moves inside the compat adapter and is deleted from the public gateway module in the same change.
- Do not teach the user a port, a Bearer key, or `hermes gateway run`.
- Do not send a Hermes `session_id`.
- Do not let a host exception leave `QThread.run`.
