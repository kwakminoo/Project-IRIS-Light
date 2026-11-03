from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from iris.engine import (
    CancelToken,
    ChatTranscript,
    Engine,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EngineReady,
    ExternalGateway,
    InternalSidecar,
    StatelessTurn,
    TurnCancelled,
    TurnFailed,
    parse_engine_source,
    shared_engine,
)
from iris.engine.runtime import _turn_api_key, reset_shared_engine
from iris.infrastructure.hermes_client import HermesInferenceTarget


def _turn(*, cancelled: bool = False) -> StatelessTurn:
    token = CancelToken()
    if cancelled:
        token.cancel()
    return StatelessTurn(
        transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
        model=HermesInferenceTarget(model="llama3.2", provider="custom"),
        cancel=token,
    )


class SharedEngineTests(TestCase):
    def setUp(self) -> None:
        reset_shared_engine()

    def tearDown(self) -> None:
        reset_shared_engine()

    def test_shared_engine_is_public_and_reset_is_not(self) -> None:
        import iris.engine as engine

        self.assertIn("shared_engine", engine.__all__)
        self.assertIn("Engine", engine.__all__)
        self.assertIn("EngineReady", engine.__all__)
        self.assertIn("EngineFailed", engine.__all__)
        self.assertNotIn("reset_shared_engine", engine.__all__)

    def test_shared_engine_returns_the_same_object(self) -> None:
        first = shared_engine()
        second = shared_engine()
        self.assertIs(first, second)

    def test_shutdown_twice_does_not_raise(self) -> None:
        engine = shared_engine()
        engine.shutdown()
        engine.shutdown()


class EngineReadyStubTests(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.home = EngineHome(Path(self._tmp.name))
        self._install = patch("iris.engine.runtime.install_into")
        self._install.start()
        self.addCleanup(self._install.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _internal(self) -> InternalSidecar:
        return InternalSidecar(home=self.home)

    def test_ensure_ready_on_fresh_sidecar_is_not_installed(self) -> None:
        engine = Engine(self._internal())
        result = engine.ensure_ready()
        self.assertIsInstance(result, EngineFailed)
        self.assertEqual(result.error.code, EngineErrorCode.NOT_INSTALLED)
        self.assertTrue(result.user_message)

    def test_run_turn_yields_one_turn_failed(self) -> None:
        engine = Engine(self._internal())
        events = list(engine.run_turn(_turn()))
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], TurnFailed)
        assert isinstance(events[0], TurnFailed)
        self.assertEqual(events[0].error.code, EngineErrorCode.NOT_INSTALLED)

    def test_cancelled_turn_yields_turn_cancelled(self) -> None:
        engine = Engine(self._internal())
        events = list(engine.run_turn(_turn(cancelled=True)))
        self.assertEqual(events, [TurnCancelled()])

    def test_mid_turn_cancel_kills_child_and_yields_cancelled(self) -> None:
        from unittest.mock import MagicMock

        engine = Engine(self._internal())
        fake = MagicMock()
        fake.poll.return_value = None
        engine._child = fake
        token = CancelToken()
        turn = StatelessTurn(
            transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
            model=HermesInferenceTarget(model="llama3.2", provider="custom"),
            cancel=token,
        )

        def read(*_a, **_k):
            token.cancel()
            return ""

        with (
            patch.object(
                engine,
                "ensure_ready",
                return_value=EngineReady(self._internal(), "ready"),
            ),
            patch.object(engine, "_write_turn"),
            patch("iris.engine.runtime._readline_timeout", side_effect=read),
            patch.object(engine, "_forget_child") as forget,
        ):
            events = list(engine.run_turn(turn))
        self.assertEqual(events, [TurnCancelled()])
        forget.assert_called()

    def test_ollama_turn_sends_compat_api_key(self) -> None:
        turn = StatelessTurn(
            transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
            model=HermesInferenceTarget(
                model="gemma4:e2b",
                provider="custom",
                base_url="http://127.0.0.1:11434/v1",
            ),
            cancel=CancelToken(),
        )
        self.assertEqual(_turn_api_key(turn), "ollama")
        keyed = StatelessTurn(
            transcript=turn.transcript,
            model=HermesInferenceTarget(
                model="gpt",
                provider="custom",
                base_url="https://api.example/v1",
                api_key="sk-user",
            ),
            cancel=CancelToken(),
        )
        self.assertEqual(_turn_api_key(keyed), "sk-user")


class ParseEngineSourceTests(TestCase):
    def test_default_is_internal_sidecar(self) -> None:
        source = parse_engine_source(object())
        self.assertIsInstance(source, InternalSidecar)
        assert isinstance(source, InternalSidecar)
        from iris.infrastructure.agent_runtime import iris_agent_home

        self.assertEqual(source.home, iris_agent_home())
        self.assertTrue(source.kill_on_shutdown)

    def test_external_flag_yields_gateway_that_does_not_kill(self) -> None:
        source = parse_engine_source(
            SimpleNamespace(
                hermes_external_gateway=True,
                hermes_base_url="http://127.0.0.1:8642/v1",
                hermes_api_key="k",
            )
        )
        self.assertIsInstance(source, ExternalGateway)
        assert isinstance(source, ExternalGateway)
        self.assertEqual(source.base_url, "http://127.0.0.1:8642/v1")
        self.assertEqual(source.api_key, "k")
        self.assertFalse(source.kill_on_shutdown)
        Engine(source).shutdown()

    def test_user_message_covers_each_code(self) -> None:
        for code in EngineErrorCode:
            message = EngineError(code, "detail").user_message
            self.assertTrue(message)
            self.assertIsInstance(message, str)
