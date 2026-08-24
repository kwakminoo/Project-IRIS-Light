"""시작 프로토콜 — 클라우드 스텁만으로는 Core가 통과하면 안 된다."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from iris.system.setup_protocol import (
    DEFAULT_MIN_MODEL,
    SetupProtocol,
    has_usable_inference_backend,
    local_inference_models,
)


class LocalVsCloudModelTests(TestCase):
    def test_cloud_stubs_are_not_local_inference_models(self) -> None:
        self.assertEqual(
            local_inference_models(
                ["gemma4:31b-cloud", "minimax-m3:cloud", "gemma4:e2b:cloud"]
            ),
            [],
        )
        self.assertEqual(
            local_inference_models(["gemma4:e2b", "gemma4:31b-cloud"]),
            ["gemma4:e2b"],
        )

    def test_usable_backend_requires_local_or_cloud_login(self) -> None:
        self.assertFalse(
            has_usable_inference_backend(["gemma4:31b-cloud"], cloud_signed_in=False)
        )
        self.assertTrue(
            has_usable_inference_backend(["gemma4:31b-cloud"], cloud_signed_in=True)
        )
        self.assertTrue(
            has_usable_inference_backend(["llama3.2:latest"], cloud_signed_in=False)
        )


class SetupProtocolModelChoiceTests(TestCase):
    def test_cloud_settings_fall_back_to_local_min_model(self) -> None:
        proto = SetupProtocol(
            min_model="gemma4:31b-cloud", simulate=False, dry_run=False
        )
        self.assertEqual(proto._local_min_model(), DEFAULT_MIN_MODEL)
        self.assertEqual(proto._cloud_min_model(), "gemma4:31b-cloud")


class VerifyCoreChatReadyTests(TestCase):
    def _proto(self) -> SetupProtocol:
        return SetupProtocol(simulate=False, dry_run=False)

    @patch("iris.system.setup_protocol.ollama_cloud_signed_in", return_value=False)
    @patch(
        "iris.system.setup_protocol._list_ollama_model_names",
        return_value=["gemma4:31b-cloud"],
    )
    @patch("iris.system.setup_protocol.is_ollama_running", return_value=True)
    def test_inspect_fails_when_only_cloud_stubs_and_not_signed_in(self, *_args) -> None:
        ok, detail = self._proto().verify_core()
        self.assertFalse(ok)
        self.assertIn("로컬 모델", detail)

    @patch("iris.system.setup_protocol.verify_iris_mcp_tools", return_value=(True, "ok"))
    @patch(
        "iris.infrastructure.hermes_client.HermesClient.probe_chat_auth",
        return_value="ok",
    )
    @patch("iris.system.setup_protocol.is_hermes_gateway_running", return_value=True)
    @patch("iris.system.setup_protocol.ollama_cloud_signed_in", return_value=True)
    @patch(
        "iris.system.setup_protocol._list_ollama_model_names",
        return_value=["gemma4:31b-cloud"],
    )
    @patch("iris.system.setup_protocol.is_ollama_running", return_value=True)
    def test_cloud_login_without_local_weights_is_enough(self, *_args) -> None:
        ok, detail = self._proto().verify_core()
        self.assertTrue(ok)
        self.assertIn("클라우드", detail)

    @patch("iris.system.setup_protocol.verify_iris_mcp_tools", return_value=(True, "ok"))
    @patch(
        "iris.infrastructure.hermes_client.HermesClient.probe_chat_auth",
        return_value="unauthorized",
    )
    @patch("iris.system.setup_protocol.is_hermes_gateway_running", return_value=True)
    @patch("iris.system.setup_protocol.ollama_cloud_signed_in", return_value=False)
    @patch(
        "iris.system.setup_protocol._list_ollama_model_names",
        return_value=["gemma4:e2b"],
    )
    @patch("iris.system.setup_protocol.is_ollama_running", return_value=True)
    def test_inspect_fails_on_chat_401_even_if_health_ok(self, *_args) -> None:
        ok, detail = self._proto().verify_core()
        self.assertFalse(ok)
        self.assertIn("401", detail)


class OllamaModelStepTests(TestCase):
    @patch("iris.system.setup_protocol.save_setup_state")
    @patch("iris.system.setup_protocol.SetupProtocol._persist_iris_model")
    @patch("iris.system.setup_protocol.SetupProtocol._pull_ollama_model", return_value=None)
    @patch("iris.system.setup_protocol.ollama_cloud_signed_in", return_value=False)
    @patch("iris.system.setup_protocol.ensure_ollama_running", return_value=True)
    @patch("iris.system.setup_protocol._list_ollama_model_names")
    def test_pulls_local_min_when_only_cloud_stubs(
        self, list_names, _ensure, _signed, pull, persist, _save
    ) -> None:
        list_names.side_effect = [["gemma4:31b-cloud"], ["gemma4:e2b"]]
        proto = SetupProtocol(min_model="gemma4:e2b", simulate=False, dry_run=False)
        result = proto._step_ollama_model()
        pull.assert_called_once()
        self.assertEqual(result.status, "done")
        persist.assert_called()

    @patch("iris.system.setup_protocol.save_setup_state")
    @patch("iris.system.setup_protocol.SetupProtocol._persist_iris_model")
    @patch("iris.system.setup_protocol.SetupProtocol._pull_ollama_model")
    @patch("iris.system.setup_protocol.ollama_cloud_signed_in", return_value=True)
    @patch("iris.system.setup_protocol.ensure_ollama_running", return_value=True)
    @patch(
        "iris.system.setup_protocol._list_ollama_model_names",
        return_value=["gemma4:31b-cloud"],
    )
    def test_skips_download_when_cloud_signed_in(
        self, _list, _ensure, _signed, pull, persist, _save
    ) -> None:
        proto = SetupProtocol(min_model="gemma4:e2b", simulate=False, dry_run=False)
        result = proto._step_ollama_model()
        pull.assert_not_called()
        self.assertEqual(result.status, "done")
        self.assertIn("클라우드", result.message)
        persist.assert_called()
