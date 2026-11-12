r"""Stream token usage wiring contract.

Run: ``.venv\Scripts\python.exe -m iris.ui._check_stream_token_usage``
"""

from __future__ import annotations

import inspect


def main() -> None:
    import json
    from io import BytesIO
    from unittest.mock import patch
    from urllib.error import HTTPError

    from iris.runtime.stream_usage import TokenUsage, parse_stream_usage

    assert parse_stream_usage(
        {"usage": {"prompt_tokens": 12, "completion_tokens": 7}}
    ) == TokenUsage(12, 7)
    assert parse_stream_usage(
        {"usage": {"input_tokens": "4", "output_tokens": "3"}}
    ) == TokenUsage(4, 3)
    assert parse_stream_usage({"prompt_eval_count": 9, "eval_count": 5}) == TokenUsage(
        9, 5
    )
    assert parse_stream_usage({"usage": {"prompt_tokens": -1}}) == TokenUsage()
    assert parse_stream_usage({}) is None
    assert parse_stream_usage("bad") is None

    # Some OpenAI-compatible servers reject stream_options. Usage collection
    # must then degrade to a normal stream instead of breaking chat.
    from iris.infrastructure import openai_compat_client as oai

    oai_bodies: list[dict] = []

    def fake_oai_open(req, timeout=0):
        body = json.loads(req.data.decode())
        oai_bodies.append(body)
        if "stream_options" in body:
            raise HTTPError(
                req.full_url,
                400,
                "bad request",
                None,
                BytesIO(b'{"error":"unknown stream_options"}'),
            )
        return BytesIO(b"data: [DONE]\n\n")

    with patch.object(oai, "urlopen", fake_oai_open):
        list(oai.stream_chat("https://example.test/v1", "k", "m", []))
    assert "stream_options" in oai_bodies[0]
    assert "stream_options" not in oai_bodies[1]

    from iris.infrastructure import iris_agent_client as hermes

    hermes_bodies: list[dict] = []

    def fake_hermes_open(req, timeout=0):
        body = json.loads(req.data.decode())
        hermes_bodies.append(body)
        if "stream_options" in body:
            raise HTTPError(
                req.full_url,
                400,
                "bad request",
                None,
                BytesIO(b'{"error":"unknown stream_options"}'),
            )
        return BytesIO(b"data: [DONE]\n\n")

    client = hermes.IrisAgentClient("http://127.0.0.1:9/v1", api_key="k")
    with patch.object(hermes, "urlopen", fake_hermes_open):
        list(client.stream_chat("m", [], provider="custom"))
    assert "stream_options" in hermes_bodies[0]
    assert "stream_options" not in hermes_bodies[1]

    from iris.ui.window.main_window import MainWindow
    from iris.ui.workers.api_provider_workers import OpenAICompatChatWorker
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker
    from iris.ui.workers.ollama_workers import OllamaChatWorker

    window = MainWindow.__new__(MainWindow)
    window._turn_usage = TokenUsage()
    MainWindow._on_chat_usage(window, 21, 8)
    assert window._turn_usage == TokenUsage(21, 8)

    for worker in (OllamaChatWorker, OpenAICompatChatWorker, IrisAgentChatWorker):
        assert hasattr(worker, "usage"), worker.__name__
    assert "tokens_in=usage.tokens_in" in inspect.getsource(
        MainWindow._finish_current_turn
    )
    print("stream token usage self-check ok")


if __name__ == "__main__":
    main()
