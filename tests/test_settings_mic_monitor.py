"""Settings 다이얼로그가 자체 AudioRecorder를 만들지 않는지."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase


class SettingsMicMonitorTests(TestCase):
    def test_settings_dialog_does_not_start_monitor(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "iris" / "ui" / "settings" / "settings_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("self._mic_monitor = AudioRecorder", src)
        self.assertNotIn("start_monitor(", src)
