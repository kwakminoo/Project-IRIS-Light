# Use the internal engine

IRIS starts Hermes for you. The user never installs Hermes, never runs `hermes gateway`, and never points the app at `:8642`.

Chat, BrowserSession, YouTube, the mini-player, Ollama as a model, Control Surface tools, and SQLite history stay where they are. You change three call sites.

## What you import

```python
from iris.engine import (
    EngineFailed,
    EngineReady,
    shared_engine,
    ContentDelta,
    ToolProgress,
    TurnFinished,
    TurnFailed,
    TurnCancelled,
    StatelessTurn,
    ChatTranscript,
)
```

`shared_engine()` is the process-wide handle. It owns the sidecar. Callers do not pass a URL, an API key, or a Hermes command.

## Ready means the sidecar answers

`ensure_ready()` installs if needed, starts the Hermes-venv sidecar if it is down, and syncs `iris-control`. It is safe to call twice. A second call that finds a live sidecar returns `EngineReady` and does no spawn.

```python
result = shared_engine().ensure_ready()
if isinstance(result, EngineFailed):
    # show result.user_message; do not raise into a Qt slot
    ...
# result is EngineReady
```

Default source is the sidecar. External `:8642` is a settings parse, not a second chat API.

## Send a turn

Build a `StatelessTurn` from the SQLite transcript IRIS already has. Do not pass a Hermes `session_id`.

```python
turn = StatelessTurn(
    transcript=ChatTranscript.parse(messages),
    model=target,
    cancel=cancel_token,
)
for event in shared_engine().run_turn(turn):
    ...
```

`run_turn` calls `ensure_ready` first. A chat send works even if the boot health worker has not finished.

## Close IRIS

`shutdown()` stops the sidecar. A second close is a no-op. An attached external gateway is not killed.

## Call site 1. Boot health worker

Today `HermesHealthWorker.run` in `iris/ui/workers/hermes_workers.py` calls `ensure_hermes_provider_config`, `sync_iris_control`, `restart_hermes_gateway`, and `verify_iris_mcp_tools`. Replace that body with the engine. Keep the QThread and the `finished_ok` / `failed` / `notice` signals.

```python
# iris/ui/workers/hermes_workers.py  HermesHealthWorker.run
def run(self) -> None:
    try:
        result = shared_engine().ensure_ready()
        if isinstance(result, EngineFailed):
            self.failed.emit(result.user_message)
            return
        if result.summary:
            self.notice.emit(result.summary)
        self.finished_ok.emit(True)
    except Exception as exc:
        self.failed.emit(str(exc))
```

Exceptions stay in `run()`. They do not reach a Qt slot. That path is `0xC0000409`.

## Call site 2. Chat worker

Today `HermesChatWorker` takes `base_url`, `api_key`, and `command`, then POSTs SSE through `HermesClient`. Drop those three arguments. Keep the Qt signals (`content_chunk`, `tool_progress`, `finished_ok`, `failed`, `request_cancel`). `_launch_chat_turn_bound` in `iris/ui/window/main_window.py` still constructs this worker. It stops passing URL and key.

```python
# iris/ui/workers/hermes_workers.py  HermesChatWorker.run  (one attempt)
turn = StatelessTurn(
    transcript=ChatTranscript.parse(attempt.messages),
    model=attempt.target,  # required. _launch_chat_turn_bound always resolves it.
    cancel=self._cancel_token,
)
content_parts: list[str] = []
for event in shared_engine().run_turn(turn):
    if isinstance(event, ContentDelta):
        content_parts.append(event.text)
        self.content_chunk.emit(event.text)
    elif isinstance(event, ToolProgress):
        self.tool_progress.emit(event.label)
    elif isinstance(event, TurnFinished):
        self.finished_ok.emit("".join(content_parts) or event.text)
        return
    elif isinstance(event, TurnCancelled):
        return
    elif isinstance(event, TurnFailed):
        last_error = event.error.user_message
        break
```

Model failover stays in the worker. `decide_fallback` still rotates `ChatAttempt` values through the same engine. It does not construct `OllamaChatWorker`.

`request_cancel` sets the `CancelToken`. The engine interrupts the sidecar. It does not close a `:8642` socket, because the default path has none.

## Call site 3. Window close

Today `MainWindow.closeEvent` in `iris/ui/window/main_window.py` stops Control Surface, chat workers, and TTS. It does not stop Hermes. Add one call after `stop_control_surface(self)`.

```python
# iris/ui/window/main_window.py  closeEvent
stop_control_surface(self)
shared_engine().shutdown()
```

`shutdown` must not raise. Log and continue if the sidecar is already gone.

## What you do not call

- `ensure_hermes_gateway_running`, `restart_hermes_gateway`, `is_hermes_gateway_running` on the default path
- `HermesClient(base_url, api_key=...)` from a worker
- `from run_agent import AIAgent` inside the Qt process
- `hermes gateway run` as a user step

`HermesClient` remains private to the external-gateway adapter. SetupProtocol first-run steps that used to clone into `%LOCALAPPDATA%\hermes` call `ensure_ready` instead. Same function as boot.

## Approval for file and terminal work

The engine does not own approval. Control Surface already has HUD confirm (`ActionSpec.confirm_required`, `ask_human`). `args.confirm` is ignored. A confirm action without a HUD is rejected (`iris/ui/control_actions/hosts.py`).

Flip `confirm_required=True` on `project.write_file`, `project.run`, and `project.rename_file` in `iris/ui/control_actions/project.py`. Those three are `risk="medium"` today and skip the HUD. Browser, YouTube, and the mini-player stay on `BrowserSession` and do not gain a confirm.

## What the user sees

1. Start IRIS.
2. Wait until the health worker reports ready, or just send. The first send starts the sidecar if needed.
3. Chat and tool turns work. File write and `project.run` ask in the existing HUD.
4. Close IRIS. The sidecar dies. Nothing keeps port 8642.
