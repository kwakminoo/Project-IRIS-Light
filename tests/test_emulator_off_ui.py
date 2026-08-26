"""에뮬 제어가 Qt 메인 스레드를 막지 않는지 — Windows 응답 없음 회귀 방지."""

from __future__ import annotations

import unittest
from pathlib import Path

from iris.system.control_surface import runs_off_ui_thread


class EmulatorOffUiTests(unittest.TestCase):
    def test_emulator_actions_run_off_ui(self) -> None:
        for name in (
            "emulator.launch",
            "emulator.kill",
            "emulator.wait_ready",
            "emulator.status",
            "emulator.install",
        ):
            self.assertTrue(runs_off_ui_thread(name), name)

    def test_ui_actions_stay_on_ui(self) -> None:
        for name in ("get_state", "ping", "window.minimize", "workspace.open_mobile"):
            self.assertFalse(runs_off_ui_thread(name), name)

    def test_control_surface_invoke_skips_invoker_for_emulator(self) -> None:
        src = Path("iris/system/control_surface.py").read_text(encoding="utf-8")
        post = src.split("def do_POST", 1)[1].split("class QuietHTTPServer", 1)[0]
        self.assertIn("runs_off_ui_thread(action)", post)
        self.assertIn("body = _run()", post)

    def test_get_state_uses_fast_emulator_status(self) -> None:
        src = Path("iris/ui/control_bindings.py").read_text(encoding="utf-8")
        self.assertIn("emulator_status_fast", src)
        self.assertIn("is_emulator_process_up", src)
        fields = src.split("def _emulator_state_fields", 1)[1].split(
            "\n# typing alias", 1
        )[0]
        self.assertNotIn("emulator_status()", fields)


if __name__ == "__main__":
    unittest.main()
