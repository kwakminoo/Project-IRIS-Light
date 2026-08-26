"""할당량 게이지 비율·색상 자검."""

from __future__ import annotations

import sys
import unittest

from iris.infrastructure.api_quota import ApiQuota
from iris.ui.monitor.system_metrics_panel import (
    _QUOTA_COLOR_HIGH,
    _QUOTA_COLOR_LOW,
    _QUOTA_COLOR_MID,
    _quota_fill_color,
)


class QuotaGaugeColorTests(unittest.TestCase):
    def test_color_bands(self) -> None:
        self.assertEqual(_quota_fill_color(0), _QUOTA_COLOR_LOW)
        self.assertEqual(_quota_fill_color(30), _QUOTA_COLOR_LOW)
        self.assertEqual(_quota_fill_color(39.9), _QUOTA_COLOR_LOW)
        self.assertEqual(_quota_fill_color(40), _QUOTA_COLOR_MID)
        self.assertEqual(_quota_fill_color(70), _QUOTA_COLOR_MID)
        self.assertEqual(_quota_fill_color(79.9), _QUOTA_COLOR_MID)
        self.assertEqual(_quota_fill_color(80), _QUOTA_COLOR_HIGH)
        self.assertEqual(_quota_fill_color(100), _QUOTA_COLOR_HIGH)

    def test_apply_quota_sets_ratio_and_color(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from iris.ui.monitor.system_metrics_panel import SystemMetricsPanel

        app = QApplication.instance() or QApplication(sys.argv)
        panel = SystemMetricsPanel()
        panel.apply_quotas(
            [
                ApiQuota(key="sess", label="SESS", used=25.0, total=100),
                ApiQuota(key="week", label="WEEK", used=55.0, total=100),
                ApiQuota(key="serp", label="SERP", used=90, total=100),
            ]
        )
        app.processEvents()
        sess = panel._api_rows["sess"]
        week = panel._api_rows["week"]
        serp = panel._api_rows["serp"]
        self.assertAlmostEqual(sess._bar._ratio, 0.25, places=3)
        self.assertAlmostEqual(week._bar._ratio, 0.55, places=3)
        self.assertAlmostEqual(serp._bar._ratio, 0.90, places=3)
        self.assertEqual(sess._bar._color.name(), _QUOTA_COLOR_LOW)
        self.assertEqual(week._bar._color.name(), _QUOTA_COLOR_MID)
        self.assertEqual(serp._bar._color.name(), _QUOTA_COLOR_HIGH)
        self.assertEqual(sess._usage.text(), "25%")

    def test_ready_message_mentions_first_utterance(self) -> None:
        from pathlib import Path

        src = Path("iris/ui/window/main_window.py").read_text(encoding="utf-8")
        chunk = src.split("def _ready_status_message", 1)[1].split(
            "def _on_intro_finished", 1
        )[0]
        self.assertIn("첫 발화에는 약간의 시간이 소요될 수 있습니다", chunk)
        ok_src = src.split("def _on_emu_launch_ok", 1)[1].split(
            "def _on_emu_launch_err", 1
        )[0]
        self.assertIn("약간의 시간이 소요될 수 있습니다", ok_src)


if __name__ == "__main__":
    unittest.main()
