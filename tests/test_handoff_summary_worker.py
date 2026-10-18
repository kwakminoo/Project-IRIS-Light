"""인수인계 요약 워커 — 세 백엔드 모두에서 구 모델을 불러 텍스트만 걷어온다."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.workers.handoff_summary_worker import (  # noqa: E402
    HandoffSummaryWorker,
    SummaryRoute,
)

MESSAGES = [
    {"role": "user", "content": "원래 요구사항"},
    {"role": "user", "content": "아이리스 인수인계 작업: …"},
]


def _chunks(text: str, *, key: str = "content"):
    for piece in text:
        yield {key: piece, "done": False}
    yield {key: None, "done": True}


class _Collector:
    def __init__(self, worker: HandoffSummaryWorker) -> None:
        self.ok: list[tuple[str, str]] = []
        self.failed: list[str] = []
        worker.finished_ok.connect(lambda t, a: self.ok.append((t, a)))
        worker.failed.connect(self.failed.append)


class OllamaSummaryTests(TestCase):
    def test_streams_and_joins_the_text(self) -> None:
        seen = {}

        class _Client:
            def __init__(self, base_url, timeout_sec=0):
                seen["base_url"] = base_url

            def stream_chat(self, model, messages, *, think=True):
                seen["model"] = model
                seen["think"] = think
                seen["messages"] = messages
                yield from _chunks("인수인계문")

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="ollama", model="qwen3:8b", base_url="http://x/v1"),
            MESSAGES,
            archive_id="a1",
        )
        out = _Collector(worker)
        with patch("iris.infrastructure.ollama_client.OllamaClient", _Client):
            worker.run()

        self.assertEqual(out.ok, [("인수인계문", "a1")])
        self.assertEqual(seen["model"], "qwen3:8b")
        self.assertEqual(seen["messages"], MESSAGES)
        # 사고 과정이 인수인계문에 섞이면 후임이 헷갈린다
        self.assertFalse(seen["think"])

    def test_upstream_error_is_reported_not_swallowed(self) -> None:
        class _Client:
            def __init__(self, *a, **k):
                pass

            def stream_chat(self, *a, **k):
                raise RuntimeError("Ollama HTTP 429: rate limit")
                yield  # pragma: no cover

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="ollama", model="m"), MESSAGES
        )
        out = _Collector(worker)
        with patch("iris.infrastructure.ollama_client.OllamaClient", _Client):
            worker.run()

        self.assertEqual(out.ok, [])
        self.assertIn("429", out.failed[0])

    def test_empty_answer_counts_as_failure(self) -> None:
        """빈 요약을 성공으로 올리면 규칙 기반 인수인계문이 지워진다."""

        class _Client:
            def __init__(self, *a, **k):
                pass

            def stream_chat(self, *a, **k):
                yield from _chunks("   ")

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="ollama", model="m"), MESSAGES
        )
        out = _Collector(worker)
        with patch("iris.infrastructure.ollama_client.OllamaClient", _Client):
            worker.run()

        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, ["빈 인수인계문"])

    def test_cancel_emits_nothing(self) -> None:
        class _Client:
            def __init__(self, *a, **k):
                pass

            def stream_chat(self, *a, **k):
                yield from _chunks("버려질 텍스트")

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="ollama", model="m"), MESSAGES
        )
        out = _Collector(worker)
        worker.request_cancel()
        with patch("iris.infrastructure.ollama_client.OllamaClient", _Client):
            worker.run()

        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, [])


class HermesSummaryTests(TestCase):
    def test_uses_the_resolved_upstream_model(self) -> None:
        seen = {}

        class _Client:
            def __init__(self, base_url, *, api_key="", command="hermes"):
                seen["api_key"] = api_key

            def set_inference_model(self, model, *, target=None):
                seen["inference"] = model

            def stream_chat(self, model, messages, **kwargs):
                seen["model"] = model
                seen["provider"] = kwargs.get("provider", "")
                seen["stream_keys"] = set(kwargs)
                yield from _chunks("허메스 요약")

        route = SummaryRoute(
            backend="hermes",
            model="api:ab12:friendly",
            base_url="http://127.0.0.1:8642/v1",
            api_key="key",
            target=SimpleNamespace(
                model="vendor/internal-v3", provider="custom", label="friendly"
            ),
        )
        worker = HandoffSummaryWorker(route, MESSAGES, archive_id="a2")
        out = _Collector(worker)
        with patch("iris.infrastructure.hermes_client.HermesClient", _Client):
            worker.run()

        self.assertEqual(out.ok, [("허메스 요약", "a2")])
        self.assertNotIn("inference", seen)
        self.assertEqual(seen["model"], "vendor/internal-v3")
        self.assertEqual(seen["provider"], "custom")
        self.assertNotIn("api_key", seen["stream_keys"])
        self.assertEqual(seen["api_key"], "key")

    def test_without_a_target_it_uses_the_plain_model_name(self) -> None:
        seen = {}

        class _Client:
            def __init__(self, *a, **k):
                pass

            def set_inference_model(self, model, *, target=None):
                seen["inference"] = model

            def stream_chat(self, model, messages, **kwargs):
                seen["model"] = model
                seen["provider"] = kwargs.get("provider", "")
                yield from _chunks("답")

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="hermes", model="gemma4:cloud"), MESSAGES
        )
        with patch("iris.infrastructure.hermes_client.HermesClient", _Client):
            worker.run()
        self.assertNotIn("inference", seen)
        self.assertEqual(seen["model"], "gemma4:cloud")
        self.assertEqual(seen["provider"], "")


class ApiSummaryTests(TestCase):
    def test_passes_provider_credentials_through(self) -> None:
        seen = {}

        def _stream(base_url, api_key, model, messages, *, auth_style="bearer", timeout=0):
            seen.update(
                base_url=base_url, api_key=api_key, model=model, auth_style=auth_style
            )
            yield from _chunks("API 요약")

        route = SummaryRoute(
            backend="api",
            model="gpt-x",
            base_url="https://api.example.com/v1",
            api_key="sk-1",
            auth_style="x-api-key",
        )
        worker = HandoffSummaryWorker(route, MESSAGES, archive_id="a3")
        out = _Collector(worker)
        with patch("iris.infrastructure.openai_compat_client.stream_chat", _stream):
            worker.run()

        self.assertEqual(out.ok, [("API 요약", "a3")])
        self.assertEqual(seen["model"], "gpt-x")
        self.assertEqual(seen["api_key"], "sk-1")
        self.assertEqual(seen["auth_style"], "x-api-key")

    def test_unknown_backend_falls_back_to_ollama(self) -> None:
        class _Client:
            def __init__(self, *a, **k):
                pass

            def stream_chat(self, *a, **k):
                yield from _chunks("올라마로 갔다")

        worker = HandoffSummaryWorker(
            SummaryRoute(backend="무엇인가", model="m"), MESSAGES
        )
        out = _Collector(worker)
        with patch("iris.infrastructure.ollama_client.OllamaClient", _Client):
            worker.run()
        self.assertEqual(out.ok[0][0], "올라마로 갔다")
