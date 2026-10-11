"""채팅 요청은 슬롯 모델을 유지하고, provider가 있으면 광고 이름으로 바꾸지 않는다."""

from __future__ import annotations

import json
import sys
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.infrastructure.hermes_client import HermesClient, HermesInferenceTarget  # noqa: E402
from iris.runtime.chat_run_slot import ChatRunSlot, choose_turn_model  # noqa: E402
from iris.ui.workers.hermes_workers import HermesChatWorker  # noqa: E402


def _slot() -> ChatRunSlot:
    return ChatRunSlot(conversation_id=1)


class ChooseTurnModelTests(TestCase):
    def test_followthrough_keeps_stored_model_and_skips_picker(self) -> None:
        slot = _slot()
        slot.inference_model = "model-x"

        def picker() -> str:
            raise AssertionError("picker")

        self.assertEqual(choose_turn_model(slot, picker, followthrough=True), "model-x")
        self.assertEqual(slot.inference_model, "model-x")

    def test_user_turn_stores_picker_over_previous(self) -> None:
        slot = _slot()
        slot.inference_model = "model-x"
        chosen = choose_turn_model(slot, lambda: "model-y", followthrough=False)
        self.assertEqual(chosen, "model-y")
        self.assertEqual(slot.inference_model, "model-y")

    def test_empty_slot_followthrough_uses_picker_once(self) -> None:
        slot = _slot()
        chosen = choose_turn_model(slot, lambda: "model-z", followthrough=True)
        self.assertEqual(chosen, "model-z")
        self.assertEqual(slot.inference_model, "model-z")


class _Body:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def __iter__(self):
        yield self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


class StreamChatProviderTests(TestCase):
    def _capture(self, client: HermesClient, *, provider: str) -> dict:
        captured: dict = {}

        def fake_open(req, timeout=0):
            captured["body"] = json.loads(req.data.decode())
            captured["headers"] = {key.lower(): value for key, value in req.header_items()}
            return _Body(b"data: [DONE]\n\n")

        with (
            patch.object(client, "list_models", return_value=["hermes-agent"]) as listed,
            patch("iris.infrastructure.hermes_client.urlopen", fake_open),
        ):
            list(client.stream_chat("gemma-a", [{"role": "user", "content": "hi"}], provider=provider))
        captured["listed"] = listed.call_count
        return captured

    def test_provider_keeps_requested_model(self) -> None:
        client = HermesClient("http://127.0.0.1:9/v1", api_key="not-a-real-key")
        captured = self._capture(client, provider="custom")
        self.assertEqual(captured["body"]["model"], "gemma-a")
        self.assertEqual(captured["body"]["provider"], "custom")
        self.assertNotIn("api_key", captured["body"])
        self.assertNotIn("x-hermes-session-id", captured["headers"])
        self.assertEqual(captured["listed"], 0)

    def test_without_provider_advertised_name_wins(self) -> None:
        client = HermesClient("http://127.0.0.1:9/v1", api_key="not-a-real-key")
        captured = self._capture(client, provider="")
        self.assertEqual(captured["body"]["model"], "hermes-agent")
        self.assertNotIn("provider", captured["body"])
        self.assertEqual(captured["listed"], 1)


class _FakeClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.set_calls = 0
        self.seen: list[tuple[str, str]] = []

    def set_inference_model(self, *_args, **_kwargs) -> None:
        self.set_calls += 1

    def stream_chat(self, model, messages, **kwargs):
        self.seen.append((model, str(kwargs.get("provider") or "")))
        yield {"content": "ok", "tool_progress": None, "done": True}


class ChatWorkerModelTests(TestCase):
    def test_two_targets_skip_global_model_write(self) -> None:
        client = _FakeClient()
        targets = (
            HermesInferenceTarget(model="gemma-a", provider="custom", display="A"),
            HermesInferenceTarget(model="gemma-b", provider="openrouter", display="B"),
        )
        with (
            patch("iris.ui.workers.hermes_workers.HermesClient", return_value=client),
            patch("iris.ui.workers.hermes_workers.is_hermes_gateway_running", return_value=True),
        ):
            for target in targets:
                worker = HermesChatWorker(
                    "http://127.0.0.1:8642/v1",
                    target.label,
                    [{"role": "user", "content": "hi"}],
                    target=target,
                )
                worker.run()
        self.assertEqual(client.set_calls, 0)
        self.assertEqual(client.seen, [("gemma-a", "custom"), ("gemma-b", "openrouter")])
