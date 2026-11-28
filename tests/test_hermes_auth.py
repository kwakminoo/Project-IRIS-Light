"""Hermes 401 회귀 — Connected(/health)와 채팅 인증을 섞지 않는다."""

from __future__ import annotations

import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from iris.engine.types import EngineHome, EngineReady, InternalSidecar
from iris.infrastructure.iris_agent_client import IrisAgentClient
from iris.infrastructure.iris_agent_credentials import (
    is_weak_iris_agent_api_key,
    resolve_iris_agent_api_key,
)
from iris.system.setup_protocol import (
    HERMES_MIN_OLLAMA_NUM_CTX,
    SetupProtocol,
    _detail_looks_like_ctx_below_min,
    _ollama_provider_model,
)


def _fake_engine_ready() -> EngineReady:
    return EngineReady(
        InternalSidecar(home=EngineHome(Path("."))),
        "engine is ready",
    )


class WeakHermesApiKeyTests(TestCase):
    def test_empty_and_short_are_weak(self) -> None:
        self.assertTrue(is_weak_iris_agent_api_key(""))
        self.assertTrue(is_weak_iris_agent_api_key("   "))
        self.assertTrue(is_weak_iris_agent_api_key("short-key-only"))
        self.assertTrue(is_weak_iris_agent_api_key("x" * 23))

    def test_placeholder_markers_are_weak(self) -> None:
        self.assertTrue(is_weak_iris_agent_api_key("change-me-please-long-enough"))
        self.assertTrue(is_weak_iris_agent_api_key("please-replace-me-xxxxxxxxxx"))
        self.assertTrue(is_weak_iris_agent_api_key("your-api-key-goes-here-now"))
        self.assertTrue(is_weak_iris_agent_api_key("todo-fill-this-in-xxxxxxxxxxx"))
        self.assertTrue(is_weak_iris_agent_api_key("this-is-a-placeholder-value"))

    def test_strong_token_is_kept(self) -> None:
        strong = secrets.token_urlsafe(32)
        # 드물게 marker 부분문자열이 들어가면 재발급 대상 — 그때는 다시 뽑는다
        if is_weak_iris_agent_api_key(strong):
            strong = "A" * 32
        self.assertFalse(is_weak_iris_agent_api_key(strong))
        self.assertFalse(is_weak_iris_agent_api_key("x" * 32))


class OllamaProviderModelCtxTests(TestCase):
    def test_sets_ollama_num_ctx_when_missing(self) -> None:
        m = _ollama_provider_model({}, "exaone3.5:2.4b")
        self.assertEqual(m.get("provider"), "ollama")
        self.assertGreaterEqual(int(m.get("ollama_num_ctx") or 0), HERMES_MIN_OLLAMA_NUM_CTX)
        self.assertEqual(m.get("default"), "exaone3.5:2.4b")

    def test_keeps_larger_ctx(self) -> None:
        m = _ollama_provider_model({"ollama_num_ctx": 128000}, "gemma4:e2b")
        self.assertEqual(m.get("ollama_num_ctx"), 128000)

    def test_raises_small_ctx(self) -> None:
        m = _ollama_provider_model({"ollama_num_ctx": 32768}, "gemma4:e2b")
        self.assertEqual(m.get("ollama_num_ctx"), HERMES_MIN_OLLAMA_NUM_CTX)


class CtxBelowMinDetailTests(TestCase):
    def test_detects_hermes_ctx_message(self) -> None:
        msg = (
            "Model exaone3.5:2.4b has a context window of 32,768 tokens, "
            "which is below the minimum of 64,000"
        )
        self.assertTrue(_detail_looks_like_ctx_below_min(msg))
        self.assertFalse(_detail_looks_like_ctx_below_min("Ollama·Hermes·MCP 정상"))


class HermesEnvRotateTests(TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.home = self.root / "hermes"
        self.home.mkdir()
        self.iris_env = self.root / "iris.env"
        self._patches = [
            patch("iris.system.setup_protocol.iris_agent_home", lambda: self.home),
            patch(
                "iris.infrastructure.iris_agent_credentials.iris_agent_home",
                lambda: self.home,
            ),
            patch(
                "iris.system.setup_protocol._iris_env_path",
                lambda: self.iris_env,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._td.cleanup()

    def test_legacy_gateway_placeholder_is_not_mutated(self) -> None:
        (self.home / ".env").write_text(
            "API_SERVER_KEY=change-me-please\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        result = proto._step_iris_agent_env()
        self.assertEqual(result.status, "done", result)
        self.assertFalse(proto._hermes_key_rotated)
        self.assertIn("내부 연결", result.message)
        self.assertIn("change-me-please", (self.home / ".env").read_text(encoding="utf-8"))

    def test_strong_key_preserved(self) -> None:
        strong = "A" * 32
        (self.home / ".env").write_text(
            f"API_SERVER_KEY={strong}\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        result = proto._step_iris_agent_env()
        self.assertEqual(result.status, "done", result)
        self.assertFalse(proto._hermes_key_rotated)
        self.assertNotIn("재발급", result.message)
        self.assertIn(strong, (self.home / ".env").read_text(encoding="utf-8"))

    def test_env_step_has_no_legacy_force_rotate_api(self) -> None:
        strong = "B" * 32
        (self.home / ".env").write_text(
            f"API_SERVER_KEY={strong}\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        with self.assertRaises(TypeError):
            proto._step_iris_agent_env(force_rotate=True)
        body = (self.home / ".env").read_text(encoding="utf-8")
        self.assertIn(strong, body)


class HermesGatewayForceRestartTests(TestCase):
    def test_key_rotated_resets_shared_engine_then_ensure_ready(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._hermes_key_rotated = True
        engine = MagicMock()
        engine.ensure_ready.return_value = _fake_engine_ready()
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch("iris.engine.runtime.reset_shared_engine") as reset,
            patch(
                "iris.system.setup_protocol.sync_iris_control",
                return_value=MagicMock(summary_line=lambda: "sync ok"),
            ),
        ):
            result = proto._step_iris_agent_engine()
        self.assertEqual(result.status, "done", result)
        reset.assert_called_once()
        engine.ensure_ready.assert_called_once()
        self.assertFalse(proto._hermes_key_rotated)

    def test_happy_path_ensure_ready_without_reset(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._hermes_key_rotated = False
        engine = MagicMock()
        engine.ensure_ready.return_value = _fake_engine_ready()
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch("iris.engine.runtime.reset_shared_engine") as reset,
            patch(
                "iris.system.setup_protocol.sync_iris_control",
                return_value=MagicMock(summary_line=lambda: "sync ok"),
            ),
        ):
            result = proto._step_iris_agent_engine()
        self.assertEqual(result.status, "done", result)
        reset.assert_not_called()
        engine.ensure_ready.assert_called_once()

    def test_core_smoke_legacy_401_fails_without_gateway_mutation(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        calls: dict[str, list] = {"env": [], "gw": []}
        verifies = [(False, "[API_KEY] Hermes 채팅 401 Unauthorized")]

        def _env(*, force_rotate: bool = False):
            calls["env"].append(force_rotate)
            return proto._record_step("iris_agent_env", "done", "rotated")

        def _gw(*, force_restart: bool = False):
            calls["gw"].append(force_restart)
            return proto._record_step("iris_agent_engine", "done", "restarted")

        with (
            patch.object(proto, "verify_core", side_effect=verifies),
            patch.object(proto, "_step_iris_agent_env", side_effect=_env),
            patch.object(proto, "_step_iris_agent_engine", side_effect=_gw),
        ):
            result = proto._step_core_smoke()
        self.assertEqual(result.status, "failed", result)
        self.assertEqual(calls["env"], [])
        self.assertEqual(calls["gw"], [])


class HermesApiKeyResolveTests(TestCase):
    def test_empty_iris_key_uses_gateway_env(self) -> None:
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            self.assertEqual(resolve_iris_agent_api_key(""), "gateway-secret")
            self.assertEqual(resolve_iris_agent_api_key("   "), "gateway-secret")

    def test_stale_iris_key_does_not_override_gateway_env(self) -> None:
        """설정창에 남은 잘못된 키로 401이 나던 경로."""
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            self.assertEqual(resolve_iris_agent_api_key("wrong-from-settings"), "gateway-secret")

    def test_iris_key_used_when_gateway_env_missing(self) -> None:
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={},
        ):
            self.assertEqual(resolve_iris_agent_api_key("iris-only"), "iris-only")
            self.assertEqual(resolve_iris_agent_api_key(""), "")


class IrisAgentClientAuthTests(TestCase):
    def test_chat_client_sends_bearer_even_if_caller_passes_empty_key(self) -> None:
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = IrisAgentClient("http://127.0.0.1:8642/v1", api_key="")
            self.assertEqual(client.api_key, "gateway-secret")
            headers = client._headers(json_body=True)
            self.assertEqual(headers.get("Authorization"), "Bearer gateway-secret")

    def test_gateway_ready_false_without_key(self) -> None:
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={},
        ):
            client = IrisAgentClient("http://127.0.0.1:1/v1", api_key="")
            self.assertFalse(client.gateway_ready())
            ready = client.probe_gateway_ready()
            self.assertFalse(ready.ok)
            self.assertIn(ready.code, ("no_key", "health_fail"))

    def test_probe_gateway_ready_models_http_401(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        from iris.infrastructure.iris_agent_client import HealthProbeResult

        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "x" * 40},
        ):
            client = IrisAgentClient("http://127.0.0.1:8642/v1", api_key="")
            healthy = HealthProbeResult(
                ok=True, code="ok", url="http://127.0.0.1:8642/health"
            )
            err = HTTPError(
                "http://127.0.0.1:8642/v1/models",
                401,
                "Unauthorized",
                None,
                BytesIO(b"Invalid gateway API key"),
            )
            with (
                patch.object(client, "probe_health", return_value=healthy),
                patch(
                    "iris.infrastructure.iris_agent_client.urlopen", side_effect=err
                ),
            ):
                ready = client.probe_gateway_ready()
            self.assertFalse(ready.ok)
            self.assertTrue(ready.health_ok)
            self.assertEqual(ready.code, "models_http")
            self.assertEqual(ready.http_status, 401)
            self.assertIn("401", ready.detail)

    def test_normalize_iris_agent_openai_base_url(self) -> None:
        from iris.infrastructure.iris_agent_client import normalize_iris_agent_openai_base_url

        self.assertEqual(
            normalize_iris_agent_openai_base_url("http://127.0.0.1:8642"),
            "http://127.0.0.1:8642/v1",
        )
        self.assertEqual(
            normalize_iris_agent_openai_base_url("http://127.0.0.1:8642/v1/"),
            "http://127.0.0.1:8642/v1",
        )
        self.assertEqual(
            normalize_iris_agent_openai_base_url("http://127.0.0.1:8642/v1/v1"),
            "http://127.0.0.1:8642/v1",
        )
        client = IrisAgentClient("http://127.0.0.1:8642", api_key="x" * 40)
        self.assertEqual(client.base_url, "http://127.0.0.1:8642/v1")

    def test_probe_gateway_ready_models_404(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        from iris.infrastructure.iris_agent_client import HealthProbeResult

        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "x" * 40},
        ):
            client = IrisAgentClient("http://127.0.0.1:8642/v1", api_key="")
            healthy = HealthProbeResult(
                ok=True, code="ok", url="http://127.0.0.1:8642/health"
            )
            err = HTTPError(
                "http://127.0.0.1:8642/v1/models",
                404,
                "Not Found",
                None,
                BytesIO(b"404: Not Found"),
            )
            with (
                patch.object(client, "probe_health", return_value=healthy),
                patch(
                    "iris.infrastructure.iris_agent_client.urlopen", side_effect=err
                ),
            ):
                ready = client.probe_gateway_ready()
            self.assertFalse(ready.ok)
            self.assertEqual(ready.code, "models_404")
            self.assertEqual(ready.http_status, 404)
            self.assertIn("404", ready.detail)
            self.assertIn("라우트", ready.detail)


class HermesGatewayStepReadyTests(TestCase):
    def test_step_done_on_engine_ready(self) -> None:
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        engine = MagicMock()
        engine.ensure_ready.return_value = _fake_engine_ready()
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch(
                "iris.system.setup_protocol.sync_iris_control",
                return_value=MagicMock(summary_line=lambda: "sync ok"),
            ),
        ):
            result = proto._step_iris_agent_engine()
        self.assertEqual(result.status, "done", result.message)
        engine.ensure_ready.assert_called_once()

    def test_core_smoke_legacy_gateway_ready_failure_is_diagnostic_only(self) -> None:
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        calls: dict[str, list] = {"env": [], "gw": []}
        verifies = [(
            False,
            "[READY] /health OK 이지만 gateway_ready 실패 (models_http).\n"
            "/v1/models HTTP 401\n"
            "로컬 모델 있음 — 클라우드 불필요",
        )]

        def _env(*, force_rotate: bool = False):
            calls["env"].append(force_rotate)
            return proto._record_step("iris_agent_env", "done", "ok")

        def _gw(*, force_restart: bool = False):
            calls["gw"].append(force_restart)
            return proto._record_step("iris_agent_engine", "done", "restarted")

        with (
            patch.object(proto, "verify_core", side_effect=verifies),
            patch.object(proto, "_step_iris_agent_env", side_effect=_env),
            patch.object(proto, "_step_iris_agent_engine", side_effect=_gw),
            patch(
                "iris.system.iris_agent_gateway.probe_gateway_ready",
                return_value=type(
                    "R",
                    (),
                    {
                        "ok": False,
                        "code": "models_http",
                        "detail": "401",
                        "key_weak": False,
                        "key_len": 40,
                        "http_status": 401,
                    },
                )(),
            ),
        ):
            result = proto._step_core_smoke()
        self.assertEqual(result.status, "failed", result)
        self.assertEqual(calls["gw"], [])
        self.assertEqual(calls["env"], [])
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        calls: dict[str, list] = {"env": [], "gw": []}
        verifies = [(
            False,
            "[READY] /health OK 이지만 /v1/models 404 (models_404, key_len=43).\n"
            "/v1/models HTTP 404: 404: Not Found\n"
            "로컬 모델 있음 — 클라우드 불필요",
        )]

        def _env(*, force_rotate: bool = False):
            calls["env"].append(force_rotate)
            return proto._record_step("iris_agent_env", "done", "ok")

        def _gw(*, force_restart: bool = False):
            calls["gw"].append(force_restart)
            return proto._record_step("iris_agent_engine", "done", "restarted")

        with (
            patch.object(proto, "verify_core", side_effect=verifies),
            patch.object(proto, "_step_iris_agent_env", side_effect=_env),
            patch.object(proto, "_step_iris_agent_engine", side_effect=_gw),
            patch(
                "iris.system.iris_agent_gateway.probe_gateway_ready",
                return_value=type(
                    "R",
                    (),
                    {
                        "ok": False,
                        "code": "models_404",
                        "detail": "404",
                        "key_weak": False,
                        "key_len": 43,
                        "http_status": 404,
                    },
                )(),
            ),
            patch(
                "iris.system.setup_protocol._upsert_dotenv",
            ),
            patch(
                "iris.system.setup_protocol._iris_env_path",
                return_value=type("P", (), {"__str__": lambda s: "x"})(),
            ),
        ):
            result = proto._step_core_smoke()
        self.assertEqual(result.status, "failed", result)
        self.assertEqual(calls["gw"], [])
        self.assertEqual(calls["env"], [])
    def test_probe_unauthorized_without_key(self) -> None:
        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={},
        ):
            client = IrisAgentClient("http://127.0.0.1:1/v1", api_key="")
            self.assertEqual(client.probe_chat_auth(), "unauthorized")

    def test_probe_http_401_is_unauthorized(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = IrisAgentClient("http://127.0.0.1:8642/v1", api_key="")
            err = HTTPError(
                "http://127.0.0.1:8642/v1/chat/completions",
                401,
                "Unauthorized",
                None,
                BytesIO(b"Unauthorized"),
            )
            with patch("iris.infrastructure.iris_agent_client.urlopen", side_effect=err):
                self.assertEqual(client.probe_chat_auth(), "unauthorized")

    def test_probe_http_400_means_bearer_accepted(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        with patch(
            "iris.infrastructure.iris_agent_credentials.load_iris_agent_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = IrisAgentClient("http://127.0.0.1:8642/v1", api_key="")
            err = HTTPError(
                "http://127.0.0.1:8642/v1/chat/completions",
                400,
                "Bad Request",
                None,
                BytesIO(b"messages required"),
            )
            with patch("iris.infrastructure.iris_agent_client.urlopen", side_effect=err):
                self.assertEqual(client.probe_chat_auth(), "ok")


class HermesCloudAuthErrorTests(TestCase):
    def test_sse_cloud_401_message(self) -> None:
        from iris.infrastructure.iris_agent_errors import (
            CLOUD_AUTH_ERROR_PREFIX,
            GATEWAY_AUTH_ERROR_PREFIX,
            format_hermes_http_401,
            format_hermes_sse_error,
            looks_like_upstream_unauthorized,
        )

        self.assertTrue(looks_like_upstream_unauthorized("HTTP 401: Unauthorized"))
        msg = format_hermes_sse_error("HTTP 401: Unauthorized", model="gemma4:31b-cloud")
        self.assertIn(CLOUD_AUTH_ERROR_PREFIX, msg)
        self.assertNotIn(GATEWAY_AUTH_ERROR_PREFIX, msg)
        gw = format_hermes_http_401()
        self.assertIn(GATEWAY_AUTH_ERROR_PREFIX, gw)
        self.assertNotIn(CLOUD_AUTH_ERROR_PREFIX, gw)

    def test_tools_error_soft_message(self) -> None:
        from iris.infrastructure.iris_agent_errors import format_hermes_sse_error

        msg = format_hermes_sse_error(
            "registry.ollama.ai/library/exaone3.5:2.4b does not support tools"
        )
        self.assertIn("도구", msg)

    def test_provider_model_skips_cloud_when_unsigned(self) -> None:
        with patch(
            "iris.system.setup_protocol.ollama_cloud_signed_in",
            return_value=False,
        ):
            m = _ollama_provider_model({}, "gemma4:31b-cloud")
        self.assertNotEqual(m.get("default"), "gemma4:31b-cloud")
        self.assertFalse(m.get("default") or "")

    def test_provider_model_keeps_cloud_when_signed(self) -> None:
        with patch(
            "iris.system.setup_protocol.ollama_cloud_signed_in",
            return_value=True,
        ):
            m = _ollama_provider_model({}, "gemma4:31b-cloud")
        self.assertEqual(m.get("default"), "gemma4:31b-cloud")


if __name__ == "__main__":
    unittest.main()
