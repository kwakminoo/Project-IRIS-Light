"""Hermes 경로의 모델 자동 전환.

기본 설정이 `hermes_enabled=True` 라서 대부분의 사용자는 이 경로만 탄다.
여기서 전환이 안 되면 자동 전환 기능 자체가 없는 것과 같다.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.workers.chat_attempt import ChatAttempt  # noqa: E402
from iris.ui.workers.hermes_workers import HermesChatWorker  # noqa: E402


class _FakeHermesClient:
    """모델별로 정해진 결과를 돌려주는 가짜 Hermes 게이트웨이."""

    def __init__(self, script: dict[str, object]) -> None:
        self.script = script
        self.seen: list[tuple[str, list[dict[str, str]]]] = []
        self.inference_models: list[str] = []

    def __call__(self, base_url, *, api_key="", command="hermes"):
        return self

    def set_inference_model(self, model: str, *, target=None) -> None:
        self.inference_models.append(model)

    def stream_chat(self, model: str, messages):
        self.seen.append((model, list(messages)))
        outcome = self.script.get(model)
        if isinstance(outcome, Exception):
            raise outcome
        for piece in str(outcome or ""):
            yield {"tool_progress": None, "content": piece, "done": False}
        yield {"tool_progress": None, "content": None, "done": True}


def _target(upstream: str, label: str = ""):
    return SimpleNamespace(model=upstream, label=label or upstream)


class _Collector:
    def __init__(self, worker: HermesChatWorker) -> None:
        self.content: list[str] = []
        self.switches: list[tuple[str, str, bool]] = []
        self.ok: list[str] = []
        self.failed: list[str] = []
        self.connecting: list[str] = []
        worker.content_chunk.connect(self.content.append)
        worker.switched.connect(lambda m, r, had: self.switches.append((m, r, had)))
        worker.finished_ok.connect(self.ok.append)
        worker.failed.connect(self.failed.append)
        worker.connecting.connect(lambda m, h: self.connecting.append(m))


class HermesFailoverTests(TestCase):
    def setUp(self) -> None:
        self.msgs = [{"role": "user", "content": "원래 질문"}]
        self.handoff = [
            {"role": "system", "content": "인수인계문 + History 발췌"},
            {"role": "user", "content": "원래 질문"},
        ]

    def _run(self, attempts, client, *, gateway_up: bool = True) -> _Collector:
        worker = HermesChatWorker(
            "http://127.0.0.1:8642/v1",
            attempts[0].label,
            attempts[0].messages,
            attempts=attempts,
        )
        out = _Collector(worker)
        with (
            patch("iris.ui.workers.hermes_workers.HermesClient", client),
            patch(
                "iris.ui.workers.hermes_workers.is_hermes_gateway_running",
                return_value=gateway_up,
            ),
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running",
                return_value=gateway_up,
            ),
        ):
            worker.run()
        self.worker = worker
        return out

    def test_primary_success_needs_no_chain(self) -> None:
        client = _FakeHermesClient({"upstream-big": "답"})
        out = self._run(
            [ChatAttempt("paid:big", self.msgs, target=_target("upstream-big"))], client
        )
        self.assertEqual(out.ok, ["답"])
        self.assertEqual(out.switches, [])

    def test_quota_exhaustion_falls_over_through_hermes(self) -> None:
        client = _FakeHermesClient({
            "upstream-big": RuntimeError("Hermes HTTP 429: rate limit"),
            "upstream-free": "무료 모델 답",
        })
        out = self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt(
                    "free:small", self.handoff, free=True, target=_target("upstream-free")
                ),
            ],
            client,
        )
        self.assertEqual(out.ok, ["무료 모델 답"])
        self.assertEqual([s[0] for s in out.switches], ["free:small"])
        self.assertEqual(out.switches[0][1], "할당량 소진")
        self.assertEqual(self.worker.final_model, "free:small")

    def test_each_candidate_gets_its_own_upstream_and_body(self) -> None:
        """후보마다 상류 모델도 요청 본문도 새로 잡아야 한다 (CCR #1615)."""
        client = _FakeHermesClient({
            "upstream-big": RuntimeError("Hermes HTTP 429: quota"),
            "upstream-free": "답",
        })
        self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            client,
        )
        self.assertEqual(client.inference_models, [])
        self.assertEqual([item[0] for item in client.seen], ["upstream-big", "upstream-free"])
        self.assertEqual(client.seen[0][1], self.msgs)
        self.assertEqual(client.seen[1][1], self.handoff)
        self.assertIn("인수인계문", client.seen[1][1][0]["content"])

    def test_switched_reports_iris_model_id_not_upstream_name(self) -> None:
        """모델 선택기와 맞추려면 IRIS 런타임 id 를 올려야 한다."""
        client = _FakeHermesClient({
            "vendor/internal-name-v3": RuntimeError("Hermes HTTP 503: down"),
            "upstream-free": "답",
        })
        out = self._run(
            [
                ChatAttempt(
                    "api:ab12:some-model",
                    self.msgs,
                    target=_target("vendor/internal-name-v3"),
                ),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            client,
        )
        self.assertEqual(out.switches[0][0], "free:small")
        self.assertEqual(self.worker.final_model, "free:small")

    def test_gateway_down_is_reported_not_failed_over(self) -> None:
        """게이트웨이가 안 뜨면 어느 후보로도 못 간다 — 모델 탓이 아니다."""
        client = _FakeHermesClient({"upstream-free": "답"})
        out = self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            client,
            gateway_up=False,
        )
        self.assertEqual(out.switches, [])
        self.assertEqual(out.ok, [])
        self.assertTrue(out.failed)
        self.assertEqual(client.seen, [])

    def test_unclassifiable_error_does_not_switch(self) -> None:
        client = _FakeHermesClient({
            "upstream-big": RuntimeError("뭔가 이상함"),
            "upstream-free": "불려선 안 됨",
        })
        out = self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            client,
        )
        self.assertEqual(out.switches, [])
        self.assertEqual(len(client.seen), 1)
        self.assertTrue(out.failed)

    def test_auth_failure_moves_on_to_another_provider(self) -> None:
        """401 은 그 키/프로바이더 문제다 — 다른 후보에서 풀릴 수 있다."""
        client = _FakeHermesClient({
            "upstream-big": RuntimeError("HTTP 401: Unauthorized"),
            "upstream-free": "다른 곳이 받았다",
        })
        out = self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            client,
        )
        self.assertEqual(out.ok, ["다른 곳이 받았다"])

    def test_partial_text_flag_is_passed_on(self) -> None:
        class _Halfway(_FakeHermesClient):
            def stream_chat(self, model, messages):
                self.seen.append((model, list(messages)))
                if model == "upstream-big":
                    yield {"tool_progress": None, "content": "앞부분", "done": False}
                    raise RuntimeError("Hermes HTTP 429: rate limit")
                yield {"tool_progress": None, "content": "다시 씀", "done": True}

        out = self._run(
            [
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
            _Halfway({}),
        )
        self.assertEqual(out.switches[0][2], True)

    def test_cancel_stops_the_chain(self) -> None:
        client = _FakeHermesClient({
            "upstream-big": RuntimeError("Hermes HTTP 429: rate limit"),
            "upstream-free": "불려선 안 됨",
        })
        worker = HermesChatWorker(
            "http://127.0.0.1:8642/v1",
            "paid:big",
            self.msgs,
            attempts=[
                ChatAttempt("paid:big", self.msgs, target=_target("upstream-big")),
                ChatAttempt("free:small", self.handoff, target=_target("upstream-free")),
            ],
        )
        out = _Collector(worker)
        worker.request_cancel()
        with (
            patch("iris.ui.workers.hermes_workers.HermesClient", client),
            patch(
                "iris.ui.workers.hermes_workers.is_hermes_gateway_running",
                return_value=True,
            ),
        ):
            worker.run()
        self.assertEqual(out.switches, [])
        self.assertEqual(out.failed, [])

    def test_legacy_single_target_call_still_works(self) -> None:
        """attempts 를 안 넘기는 기존 호출부 호환."""
        client = _FakeHermesClient({"upstream-solo": "예전 방식"})
        worker = HermesChatWorker(
            "http://127.0.0.1:8642/v1",
            "solo-label",
            self.msgs,
            target=_target("upstream-solo", "solo-label"),
        )
        out = _Collector(worker)
        with (
            patch("iris.ui.workers.hermes_workers.HermesClient", client),
            patch(
                "iris.ui.workers.hermes_workers.is_hermes_gateway_running",
                return_value=True,
            ),
        ):
            worker.run()
        self.assertEqual(out.ok, ["예전 방식"])
        self.assertEqual(client.inference_models, [])
        self.assertEqual(client.seen[0][0], "upstream-solo")
