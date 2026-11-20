"""Ollama options 가드 · URL 판별 · config ollama_num_ctx 동기화."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from iris.infrastructure.iris_agent_client import HermesClient
from iris.system.iris_agent_ollama_guard import (
    apply_ollama_options_guard,
    looks_like_ollama_endpoint,
    sync_model_ollama_num_ctx,
)
from iris.system.setup_protocol import HERMES_MIN_OLLAMA_NUM_CTX

_SAMPLE = '''\
        if ollama_num_ctx:
            extra_body["options"] = {"num_ctx": ollama_num_ctx}
'''

_GUARDED = '''\
        # iris: ollama-options-guard
        if ollama_num_ctx and _looks_like_ollama_endpoint(ctx.get("base_url")):
            extra_body["options"] = {"num_ctx": ollama_num_ctx}
'''

_UNRELATED = '''\
def ping():
    return 1
'''


def _custom_init(root: Path, body: str) -> Path:
    path = root / "plugins" / "model-providers" / "custom" / "__init__.py"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


class LooksLikeOllamaTests(unittest.TestCase):
    def test_local_port_and_ollama_host(self) -> None:
        self.assertTrue(looks_like_ollama_endpoint("http://127.0.0.1:11434/v1"))
        self.assertTrue(looks_like_ollama_endpoint("https://ollama.com/v1"))
        self.assertTrue(looks_like_ollama_endpoint("https://api.ollama.com/v1"))

    def test_cloud_openai_compat_hosts_are_not_ollama(self) -> None:
        self.assertFalse(
            looks_like_ollama_endpoint(
                "https://generativelanguage.googleapis.com/v1beta/openai"
            )
        )
        self.assertFalse(
            looks_like_ollama_endpoint("https://integrate.api.nvidia.com/v1")
        )
        self.assertFalse(looks_like_ollama_endpoint("https://api.groq.com/openai/v1"))

    def test_empty_and_broken_port(self) -> None:
        self.assertFalse(looks_like_ollama_endpoint(""))
        self.assertFalse(looks_like_ollama_endpoint("   "))
        self.assertFalse(looks_like_ollama_endpoint("http://127.0.0.1:99999/v1"))


class OptionsGuardTests(unittest.TestCase):
    def test_patches_once_and_second_call_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = _custom_init(root, _SAMPLE)
            self.assertTrue(apply_ollama_options_guard(root))
            once = path.read_text(encoding="utf-8")
            self.assertIn("_looks_like_ollama_endpoint", once)
            self.assertIn("iris: ollama-options-guard", once)
            self.assertNotIn("if ollama_num_ctx:\n", once)
            self.assertFalse(apply_ollama_options_guard(root))
            self.assertEqual(path.read_text(encoding="utf-8"), once)
            self.assertEqual(once, _GUARDED)

    def test_missing_pattern_keeps_original(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = _custom_init(root, _UNRELATED)
            self.assertFalse(apply_ollama_options_guard(root))
            self.assertEqual(path.read_text(encoding="utf-8"), _UNRELATED)

    def test_missing_file_does_not_create(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(apply_ollama_options_guard(root))
            self.assertFalse(
                (root / "plugins" / "model-providers" / "custom" / "__init__.py").exists()
            )


class OllamaNumCtxSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.home = Path(self._td.name)
        self.path = self.home / "config.yaml"
        self._patch = patch(
            "iris.infrastructure.iris_agent_credentials.hermes_home",
            lambda: self.home,
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._td.cleanup()

    def _write(self, model: dict) -> None:
        self.path.write_text(
            yaml.safe_dump({"model": model}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _model(self) -> dict:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        return data["model"]

    def test_gemini_and_nvidia_drop_key_ollama_restores_floor(self) -> None:
        self._write({"provider": "custom", "ollama_num_ctx": 64000, "api_key": "keep-me"})
        sync_model_ollama_num_ctx(
            "https://generativelanguage.googleapis.com/v1beta/openai"
        )
        self.assertNotIn("ollama_num_ctx", self._model())
        self.assertEqual(self._model().get("api_key"), "keep-me")
        sync_model_ollama_num_ctx("https://integrate.api.nvidia.com/v1")
        self.assertNotIn("ollama_num_ctx", self._model())
        sync_model_ollama_num_ctx("http://127.0.0.1:11434/v1")
        self.assertGreaterEqual(
            int(self._model().get("ollama_num_ctx") or 0),
            HERMES_MIN_OLLAMA_NUM_CTX,
        )

    def test_ollama_keeps_larger_ctx_and_raises_small(self) -> None:
        self._write({"ollama_num_ctx": 128000})
        sync_model_ollama_num_ctx("http://127.0.0.1:11434/v1")
        self.assertEqual(self._model().get("ollama_num_ctx"), 128000)
        self._write({"ollama_num_ctx": 32768})
        sync_model_ollama_num_ctx("http://127.0.0.1:11434/v1")
        self.assertEqual(self._model().get("ollama_num_ctx"), HERMES_MIN_OLLAMA_NUM_CTX)


class SetInferenceModelSyncTests(unittest.TestCase):
    def test_api_success_drops_ctx_for_gemini_url(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path = home / "config.yaml"
            path.write_text(
                yaml.safe_dump(
                    {"model": {"ollama_num_ctx": 64000, "api_key": "stored"}},
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            client = HermesClient("http://127.0.0.1:8642/v1")
            with (
                patch(
                    "iris.infrastructure.iris_agent_credentials.hermes_home",
                    lambda: home,
                ),
                patch.object(client, "_set_model_via_api", return_value=True),
            ):
                client.set_inference_model(
                    "gemini-2.0-flash",
                    provider="custom",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    api_key="live-secret-not-for-yaml-argv",
                )
            model = yaml.safe_load(path.read_text(encoding="utf-8"))["model"]
            self.assertNotIn("ollama_num_ctx", model)
            blob = path.read_text(encoding="utf-8")
            self.assertNotIn("live-secret-not-for-yaml-argv", blob)


if __name__ == "__main__":
    unittest.main()
