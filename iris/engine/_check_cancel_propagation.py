"""Cancel must reach running work, not only clear the UI busy flag.

1. Internal: mid-turn cancel sends cooperative stop before hard forget.
2. External: stream_chat with CancelToken exits without waiting timeout_sec.
3. Shutdown must not wait on a mid-turn event-read lock hold.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_cancel_propagation
"""

from __future__ import annotations

import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import MagicMock, patch

from iris.engine import (
    CancelToken,
    ChatTranscript,
    Engine,
    EngineReady,
    InternalSidecar,
    StatelessTurn,
    TurnCancelled,
)
from iris.engine.types import EngineHome
from iris.infrastructure.iris_agent_client import IrisAgentClient, IrisAgentInferenceTarget


def _check_engine_stop_before_forget() -> None:
    with TemporaryDirectory() as tmp:
        home = EngineHome(Path(tmp))
        engine = Engine(InternalSidecar(home=home))
        fake = MagicMock()
        fake.poll.return_value = None
        engine._child = fake
        token = CancelToken()
        turn = StatelessTurn(
            transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
            model=IrisAgentInferenceTarget(model="llama3.2", provider="custom"),
            cancel=token,
        )

        def read(*_a, **_k):
            token.cancel()
            return ""

        order: list[str] = []

        with (
            patch.object(
                engine,
                "ensure_ready",
                return_value=EngineReady(InternalSidecar(home=home), "ready"),
            ),
            patch.object(engine, "_write_turn"),
            patch("iris.engine.runtime._readline_timeout", side_effect=read),
            patch(
                "iris.engine.runtime._send_stop",
                side_effect=lambda *_a, **_k: order.append("stop"),
            ),
            patch.object(
                engine,
                "_forget_child",
                side_effect=lambda *_a, **_k: order.append("forget"),
            ),
        ):
            events = list(engine.run_turn(turn))

        assert events == [TurnCancelled()], events
        assert order == ["stop", "forget"], order


_HANG_RELEASE = Event()


class _HangHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        # Drain the request body first. Leaving it unread stalls urllib urlopen
        # on Windows until timeout_sec (looks like cancel never fired).
        length = int(self.headers.get("Content-Length") or 0)
        if length > 0:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        # Hold the socket open with no SSE body until the check releases us.
        while not _HANG_RELEASE.wait(0.05):
            pass

    def log_message(self, *_args) -> None:
        return


def _check_stream_cancel_beats_idle_timeout() -> None:
    _HANG_RELEASE.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HangHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    token = CancelToken()
    client = IrisAgentClient(
        f"http://127.0.0.1:{port}/v1",
        api_key="not-a-real-key",
        timeout_sec=300.0,
    )

    def cancel_soon() -> None:
        time.sleep(0.25)
        token.cancel()

    Thread(target=cancel_soon, daemon=True).start()
    started = time.monotonic()
    try:
        list(
            client.stream_chat(
                "test-model",
                [{"role": "user", "content": "hi"}],
                cancel=token,
            )
        )
    finally:
        _HANG_RELEASE.set()
        server.shutdown()
    elapsed = time.monotonic() - started
    assert elapsed < 5.0, f"stream cancel waited {elapsed:.2f}s (cap 5s, not 300s)"
    assert token.cancelled()


def _check_shutdown_not_blocked_by_turn_lock() -> None:
    """GUI closeEvent calls shutdown while run_turn may be mid-read.

    Before the lock fix, run_turn held Engine._lock across _read_turn_events, so
    shutdown blocked until the turn finished. Cap is ~2s of wall time for
    shutdown to return while a fake child is still 'mid-turn'.
    """
    with TemporaryDirectory() as tmp:
        home = EngineHome(Path(tmp))
        engine = Engine(InternalSidecar(home=home))
        fake = MagicMock()
        fake.poll.return_value = None
        engine._child = fake
        token = CancelToken()
        turn = StatelessTurn(
            transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
            model=IrisAgentInferenceTarget(model="llama3.2", provider="custom"),
            cancel=token,
        )
        in_read = Event()
        release_read = Event()
        turn_done = Event()
        turn_error: list[BaseException] = []

        def blocking_readline(*_a, **_k):
            in_read.set()
            if not release_read.wait(15.0):
                raise TimeoutError("test release_read never set")
            token.cancel()
            return ""

        def run_turn_thread() -> None:
            try:
                list(engine.run_turn(turn))
            except BaseException as exc:  # noqa: BLE001 — surface to main
                turn_error.append(exc)
            finally:
                turn_done.set()

        with (
            patch.object(
                engine,
                "ensure_ready",
                return_value=EngineReady(InternalSidecar(home=home), "ready"),
            ),
            patch.object(engine, "_write_turn"),
            patch("iris.engine.runtime._readline_timeout", side_effect=blocking_readline),
            patch("iris.engine.runtime._send_stop"),
            patch("iris.engine.runtime._terminate_child"),
            patch("iris.engine.runtime._close_pipes"),
        ):
            Thread(target=run_turn_thread, daemon=True).start()
            assert in_read.wait(5.0), "run_turn never entered event read"
            started = time.monotonic()
            engine.shutdown()
            elapsed = time.monotonic() - started
            release_read.set()
            assert turn_done.wait(5.0), "run_turn thread did not finish"
        assert not turn_error, turn_error
        assert elapsed < 2.0, f"shutdown blocked {elapsed:.2f}s by mid-turn lock (cap 2s)"
        assert engine._child is None


def main() -> None:
    _check_engine_stop_before_forget()
    _check_stream_cancel_beats_idle_timeout()
    _check_shutdown_not_blocked_by_turn_lock()
    print("ok cancel propagates (stop-before-forget + stream exit + shutdown under turn)")


if __name__ == "__main__":
    main()
