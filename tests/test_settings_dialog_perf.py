"""설정창 열기 경로 — UI 스레드 블로킹 제거 회귀."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from iris.system.setup_protocol import SetupProtocol


class SettingsDialogPerfTests(TestCase):
    def test_build_voice_box_does_not_sync_fetch_references(self) -> None:
        src = (
            Path(__file__).resolve().parents[1]
            / "iris"
            / "ui"
            / "settings"
            / "settings_dialog.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "_refresh_voice_recommendations_from_runtime(silent=True)",
            src,
        )

    def test_detect_local_skips_network(self) -> None:
        proto = SetupProtocol()
        with (
            patch(
                "iris.system.setup_protocol.is_ollama_running",
                side_effect=AssertionError("network"),
            ),
            patch(
                "iris.system.setup_protocol.is_hermes_gateway_running",
                side_effect=AssertionError("network"),
            ),
        ):
            snap = proto.detect_local()
        self.assertIsNone(snap.get("ollama_running"))
        self.assertIsNone(snap.get("hermes_running"))

    def test_enrich_detect_network_calls_health_only_timeout(self) -> None:
        proto = SetupProtocol()
        snap = proto.detect_local()
        with (
            patch(
                "iris.system.setup_protocol.is_ollama_running",
                return_value=True,
            ) as ollama,
            patch(
                "iris.system.setup_protocol.is_hermes_gateway_running",
                return_value=False,
            ) as hermes,
        ):
            out = proto.enrich_detect_network(snap, timeout_sec=0.5)
        ollama.assert_called_once()
        self.assertEqual(ollama.call_args.kwargs.get("timeout_sec"), 0.5)
        hermes.assert_called_once()
        self.assertEqual(hermes.call_args.kwargs.get("timeout_sec"), 0.5)
        self.assertTrue(out["ollama_running"])
        self.assertFalse(out["hermes_running"])
