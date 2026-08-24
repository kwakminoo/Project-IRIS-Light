"""Hermes 401 회귀 — Connected(/health)와 채팅 인증을 섞지 않는다."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from iris.infrastructure.hermes_client import HermesClient
from iris.infrastructure.hermes_credentials import resolve_hermes_api_key


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
