"""Hermes 401 회귀 — Connected(/health)와 채팅 인증을 섞지 않는다."""

from __future__ import annotations

import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from iris.infrastructure.hermes_client import HermesClient
from iris.infrastructure.hermes_credentials import (
    is_weak_hermes_api_key,
    resolve_hermes_api_key,
)
from iris.system.setup_protocol import (
    HERMES_MIN_OLLAMA_NUM_CTX,
    SetupProtocol,
    _detail_looks_like_ctx_below_min,
    _ollama_provider_model,
)


class WeakHermesApiKeyTests(TestCase):
    def test_empty_and_short_are_weak(self) -> None:
        self.assertTrue(is_weak_hermes_api_key(""))
        self.assertTrue(is_weak_hermes_api_key("   "))
        self.assertTrue(is_weak_hermes_api_key("short-key-only"))
        self.assertTrue(is_weak_hermes_api_key("x" * 23))

    def test_placeholder_markers_are_weak(self) -> None:
        self.assertTrue(is_weak_hermes_api_key("change-me-please-long-enough"))
        self.assertTrue(is_weak_hermes_api_key("please-replace-me-xxxxxxxxxx"))
        self.assertTrue(is_weak_hermes_api_key("your-api-key-goes-here-now"))
        self.assertTrue(is_weak_hermes_api_key("todo-fill-this-in-xxxxxxxxxxx"))
        self.assertTrue(is_weak_hermes_api_key("this-is-a-placeholder-value"))

    def test_strong_token_is_kept(self) -> None:
        strong = secrets.token_urlsafe(32)
        # 드물게 marker 부분문자열이 들어가면 재발급 대상 — 그때는 다시 뽑는다
        if is_weak_hermes_api_key(strong):
            strong = "A" * 32
        self.assertFalse(is_weak_hermes_api_key(strong))
        self.assertFalse(is_weak_hermes_api_key("x" * 32))


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
            patch("iris.system.setup_protocol.hermes_home", lambda: self.home),
            patch(
                "iris.infrastructure.hermes_credentials.hermes_home",
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

    def test_weak_placeholder_is_rotated(self) -> None:
        (self.home / ".env").write_text(
            "API_SERVER_KEY=change-me-please\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        result = proto._step_hermes_env()
        self.assertEqual(result.status, "done", result)
        self.assertTrue(proto._hermes_key_rotated)
        self.assertIn("재발급", result.message)
        new_key = (self.home / ".env").read_text(encoding="utf-8")
        self.assertNotIn("change-me-please", new_key)
        self.assertFalse(is_weak_hermes_api_key(resolve_hermes_api_key()))

    def test_strong_key_preserved(self) -> None:
        strong = "A" * 32
        (self.home / ".env").write_text(
            f"API_SERVER_KEY={strong}\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        result = proto._step_hermes_env()
        self.assertEqual(result.status, "done", result)
        self.assertFalse(proto._hermes_key_rotated)
        self.assertNotIn("재발급", result.message)
        self.assertIn(strong, (self.home / ".env").read_text(encoding="utf-8"))

    def test_force_rotate_replaces_strong(self) -> None:
        strong = "B" * 32
        (self.home / ".env").write_text(
            f"API_SERVER_KEY={strong}\n", encoding="utf-8"
        )
        proto = SetupProtocol(dry_run=False, simulate=False)
        result = proto._step_hermes_env(force_rotate=True)
        self.assertEqual(result.status, "done", result)
        self.assertTrue(proto._hermes_key_rotated)
        body = (self.home / ".env").read_text(encoding="utf-8")
        self.assertNotIn(strong, body)


class HermesGatewayForceRestartTests(TestCase):
    def test_already_running_restarts_when_key_rotated(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._hermes_key_rotated = True
        restart_calls: list[bool] = []

        def _restart(*_a, **_k):
            restart_calls.append(True)
            return True

        with (
            patch(
                "iris.system.hermes_gateway.is_hermes_gateway_running",
                return_value=True,
            ),
            patch(
                "iris.system.hermes_gateway.restart_hermes_gateway",
                side_effect=_restart,
            ),
            patch(
                "iris.system.hermes_gateway.ensure_hermes_gateway_running",
                return_value=True,
            ),
            patch(
                "iris.system.setup_protocol.verify_iris_mcp_tools",
                return_value=(True, "mcp ok"),
            ),
            patch(
                "iris.system.setup_protocol.resolve_hermes_api_key",
                return_value="test-key-xxxxxxxxxxxxxxxx",
            ),
        ):
            result = proto._step_hermes_gateway()
        self.assertEqual(result.status, "done", result)
        self.assertEqual(len(restart_calls), 1)
        self.assertFalse(proto._hermes_key_rotated)

    def test_already_running_kept_without_rotate(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._hermes_key_rotated = False
        restart_calls: list[bool] = []

        with (
            patch(
                "iris.system.hermes_gateway.is_hermes_gateway_running",
                return_value=True,
            ),
            patch(
                "iris.system.hermes_gateway.restart_hermes_gateway",
                side_effect=lambda *_a, **_k: restart_calls.append(True) or True,
            ),
            patch(
                "iris.system.hermes_gateway.mark_gateway_already_running",
            ),
            patch(
                "iris.system.setup_protocol.verify_iris_mcp_tools",
                return_value=(True, "mcp ok"),
            ),
            patch(
                "iris.system.setup_protocol.resolve_hermes_api_key",
                return_value="test-key-xxxxxxxxxxxxxxxx",
            ),
        ):
            result = proto._step_hermes_gateway()
        self.assertEqual(result.status, "done", result)
        self.assertEqual(len(restart_calls), 0)

    def test_core_smoke_401_force_rotates(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        calls: dict[str, list] = {"env": [], "gw": []}
        verifies = [
            (False, "[API_KEY] Hermes 채팅 401 Unauthorized"),
            (True, "Ollama·Hermes·MCP 정상"),
        ]

        def _env(*, force_rotate: bool = False):
            calls["env"].append(force_rotate)
            return proto._record_step("hermes_env", "done", "rotated")

        def _gw(*, force_restart: bool = False):
            calls["gw"].append(force_restart)
            return proto._record_step("hermes_gateway", "done", "restarted")

        with (
            patch.object(proto, "verify_core", side_effect=verifies),
            patch.object(proto, "_step_hermes_env", side_effect=_env),
            patch.object(proto, "_step_hermes_gateway", side_effect=_gw),
        ):
            result = proto._step_core_smoke()
        self.assertEqual(result.status, "done", result)
        self.assertEqual(calls["env"], [True])
        self.assertEqual(calls["gw"], [True])


class HermesApiKeyResolveTests(TestCase):
    def test_empty_iris_key_uses_gateway_env(self) -> None:
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            self.assertEqual(resolve_hermes_api_key(""), "gateway-secret")
            self.assertEqual(resolve_hermes_api_key("   "), "gateway-secret")

    def test_stale_iris_key_does_not_override_gateway_env(self) -> None:
        """설정창에 남은 잘못된 키로 401이 나던 경로."""
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            self.assertEqual(resolve_hermes_api_key("wrong-from-settings"), "gateway-secret")

    def test_iris_key_used_when_gateway_env_missing(self) -> None:
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={},
        ):
            self.assertEqual(resolve_hermes_api_key("iris-only"), "iris-only")
            self.assertEqual(resolve_hermes_api_key(""), "")


class HermesClientAuthTests(TestCase):
    def test_chat_client_sends_bearer_even_if_caller_passes_empty_key(self) -> None:
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = HermesClient("http://127.0.0.1:8642/v1", api_key="")
            self.assertEqual(client.api_key, "gateway-secret")
            headers = client._headers(json_body=True)
            self.assertEqual(headers.get("Authorization"), "Bearer gateway-secret")

    def test_gateway_ready_false_without_key(self) -> None:
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={},
        ):
            client = HermesClient("http://127.0.0.1:1/v1", api_key="")
            self.assertFalse(client.gateway_ready())
            ready = client.probe_gateway_ready()
            self.assertFalse(ready.ok)
            self.assertIn(ready.code, ("no_key", "health_fail"))

    def test_probe_gateway_ready_models_http_401(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        from iris.infrastructure.hermes_client import HealthProbeResult

        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "x" * 40},
        ):
            client = HermesClient("http://127.0.0.1:8642/v1", api_key="")
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
                    "iris.infrastructure.hermes_client.urlopen", side_effect=err
                ),
            ):
                ready = client.probe_gateway_ready()
            self.assertFalse(ready.ok)
            self.assertTrue(ready.health_ok)
            self.assertEqual(ready.code, "models_http")
            self.assertEqual(ready.http_status, 401)
            self.assertIn("401", ready.detail)


class HermesGatewayStepReadyTests(TestCase):
    def test_health_ok_models_fail_triggers_restart(self) -> None:
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        restart_calls: list[bool] = []

        def _restart(*_a, **_k):
            restart_calls.append(True)
            return True

        with (
            patch(
                "iris.system.hermes_gateway.is_hermes_gateway_running",
                side_effect=[True, False],  # health_up, ready_up
            ),
            patch(
                "iris.system.hermes_gateway.probe_gateway_ready",
                return_value=type(
                    "R",
                    (),
                    {
                        "ok": False,
                        "code": "models_http",
                        "detail": "/v1/models HTTP 401",
                        "key_weak": False,
                        "key_len": 40,
                        "models_ok": False,
                    },
                )(),
            ),
            patch(
                "iris.system.hermes_gateway.restart_hermes_gateway",
                side_effect=_restart,
            ),
            patch(
                "iris.system.hermes_gateway.ensure_hermes_gateway_running",
                return_value=True,
            ),
            patch(
                "iris.system.setup_protocol.verify_iris_mcp_tools",
                return_value=(True, "mcp ok"),
            ),
            patch(
                "iris.system.setup_protocol.resolve_hermes_api_key",
                return_value="x" * 40,
            ),
            patch.object(proto, "_step_hermes_env"),
        ):
            result = proto._step_hermes_gateway()
        self.assertEqual(result.status, "done", result.message)
        self.assertTrue(restart_calls)

    def test_core_smoke_ready_fail_restarts(self) -> None:
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        calls: dict[str, list] = {"env": [], "gw": []}
        verifies = [
            (
                False,
                "[READY] /health OK 이지만 gateway_ready 실패 (models_http).\n"
                "/v1/models HTTP 401\n"
                "로컬 모델 있음 — 클라우드 불필요",
            ),
            (True, "Ollama·Hermes·MCP 정상"),
        ]

        def _env(*, force_rotate: bool = False):
            calls["env"].append(force_rotate)
            return proto._record_step("hermes_env", "done", "ok")

        def _gw(*, force_restart: bool = False):
            calls["gw"].append(force_restart)
            return proto._record_step("hermes_gateway", "done", "restarted")

        with (
            patch.object(proto, "verify_core", side_effect=verifies),
            patch.object(proto, "_step_hermes_env", side_effect=_env),
            patch.object(proto, "_step_hermes_gateway", side_effect=_gw),
            patch(
                "iris.system.hermes_gateway.probe_gateway_ready",
                return_value=type(
                    "R",
                    (),
                    {
                        "ok": False,
                        "code": "models_http",
                        "detail": "401",
                        "key_weak": False,
                        "key_len": 40,
                    },
                )(),
            ),
        ):
            result = proto._step_core_smoke()
        self.assertEqual(result.status, "done", result)
        self.assertEqual(calls["gw"], [True])
        self.assertEqual(calls["env"], [False])


class HermesChatAuthProbeTests(TestCase):
    def test_probe_unauthorized_without_key(self) -> None:
        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={},
        ):
            client = HermesClient("http://127.0.0.1:1/v1", api_key="")
            self.assertEqual(client.probe_chat_auth(), "unauthorized")

    def test_probe_http_401_is_unauthorized(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = HermesClient("http://127.0.0.1:8642/v1", api_key="")
            err = HTTPError(
                "http://127.0.0.1:8642/v1/chat/completions",
                401,
                "Unauthorized",
                None,
                BytesIO(b"Unauthorized"),
            )
            with patch("iris.infrastructure.hermes_client.urlopen", side_effect=err):
                self.assertEqual(client.probe_chat_auth(), "unauthorized")

    def test_probe_http_400_means_bearer_accepted(self) -> None:
        from io import BytesIO
        from urllib.error import HTTPError

        with patch(
            "iris.infrastructure.hermes_credentials.load_hermes_dotenv",
            return_value={"API_SERVER_KEY": "gateway-secret"},
        ):
            client = HermesClient("http://127.0.0.1:8642/v1", api_key="")
            err = HTTPError(
                "http://127.0.0.1:8642/v1/chat/completions",
                400,
                "Bad Request",
                None,
                BytesIO(b"messages required"),
            )
            with patch("iris.infrastructure.hermes_client.urlopen", side_effect=err):
                self.assertEqual(client.probe_chat_auth(), "ok")


class HermesCloudAuthErrorTests(TestCase):
    def test_sse_cloud_401_message(self) -> None:
        from iris.infrastructure.hermes_errors import (
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
        from iris.infrastructure.hermes_errors import format_hermes_sse_error

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
