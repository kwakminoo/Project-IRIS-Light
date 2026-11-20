r"""429 cooldown wiring contract.

Run: ``.venv\Scripts\python.exe -m iris.ui._check_route_cooldown_live``
"""

from __future__ import annotations

import inspect


def main() -> None:
    from iris.runtime.model_failover import RouteCooldownBook, RouteTarget
    from iris.ui.window.main_window import MainWindow
    from iris.ui.workers.chat_attempt import ChatAttempt, decide_fallback

    step = decide_fallback(
        "HTTP 429: rate limit", 0, retry_after="2", now_monotonic=10.0
    )
    assert step is not None
    assert step.delay_ms == 2_000
    assert step.cool_until_monotonic == 12.0
    assert (
        decide_fallback("HTTP 503: upstream", 0, now_monotonic=10.0)
        .cool_until_monotonic
        is None
    )

    cool = RouteTarget("cool-model", backend="api")
    ready = RouteTarget("ready-model", backend="ollama")
    book = RouteCooldownBook()
    book.mark_cool(cool, 20.0)
    book.mark_cool(cool, 15.0)
    assert book.is_cool(cool, now_monotonic=19.0), "a shorter 429 must not cool early"

    window = MainWindow.__new__(MainWindow)
    window._route_cooldown = book
    attempts = [
        ChatAttempt(cool.model, route_target=cool),
        ChatAttempt(ready.model, route_target=ready),
    ]
    kept = MainWindow._filter_cool_attempts(window, attempts, now_monotonic=19.0)
    assert [attempt.model for attempt in kept] == [ready.model]

    MainWindow._on_route_cooled(window, ready, 30.0)
    assert book.is_cool(ready, now_monotonic=29.0)

    from iris.ui.workers.api_provider_workers import OpenAICompatChatWorker
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker
    from iris.ui.workers.ollama_workers import OllamaChatWorker

    for worker in (OllamaChatWorker, OpenAICompatChatWorker, IrisAgentChatWorker):
        assert hasattr(worker, "cooled"), worker.__name__
    assert "cooled.emit" in inspect.getsource(OllamaChatWorker.run)
    assert "cooled.emit" in inspect.getsource(OpenAICompatChatWorker.run)
    assert "cooled.emit" in inspect.getsource(IrisAgentChatWorker._run_internal)
    print("route cooldown live self-check ok")


if __name__ == "__main__":
    main()
