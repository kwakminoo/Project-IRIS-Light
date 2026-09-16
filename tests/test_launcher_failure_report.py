"""런처 — pythonw로 띄운 앱이 즉사하면 이유를 보여 줘야 한다."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import IRIS_launcher as launcher


class DiagnoseTests(unittest.TestCase):
    def test_missing_module_names_the_package_and_next_step(self) -> None:
        msg = launcher._diagnose(
            "Traceback (most recent call last):"
            "ModuleNotFoundError: No module named 'PyQt6.QtCore'"
        )
        self.assertIn("PyQt6.QtCore", msg)
        self.assertIn("setup.bat", msg)

    def test_dll_failure_points_at_vcredist(self) -> None:
        msg = launcher._diagnose("ImportError: DLL load failed while importing QtCore")
        self.assertIn("VCRedist", msg)

    def test_unknown_failure_still_reports_last_line(self) -> None:
        msg = launcher._diagnose("something odd happened")
        self.assertIn("something odd happened", msg)

    def test_empty_log_falls_back_to_setup_hint(self) -> None:
        self.assertIn("setup.bat", launcher._diagnose(""))


class RunAndWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.log = self.tmp / "launcher.log"
        self.died: list[str] = []
        patcher_log = patch.object(launcher, "_log_path", lambda: self.log)
        patcher_die = patch.object(launcher, "_die", self._fake_die)
        patcher_log.start()
        patcher_die.start()
        self.addCleanup(patcher_log.stop)
        self.addCleanup(patcher_die.stop)
        self.addCleanup(self._tmp.cleanup)

    def _fake_die(self, msg: str) -> None:
        self.died.append(msg)
        raise SystemExit(1)

    def test_silent_death_is_surfaced_with_reason(self) -> None:
        empty = self.tmp / "no-app"
        empty.mkdir()
        with self.assertRaises(SystemExit):
            launcher._run_and_watch(Path(sys.executable), empty)
        self.assertTrue(self.died)
        self.assertIn("iris", self.died[0])
        self.assertIn(str(self.log), self.died[0])

    def test_living_app_is_left_alone(self) -> None:
        root = self.tmp / "app"
        (root / "iris").mkdir(parents=True)
        (root / "iris" / "__init__.py").write_text("", encoding="utf-8")
        (root / "iris" / "__main__.py").write_text(
            "import time; time.sleep(30)", encoding="utf-8"
        )
        with patch.object(launcher, "STARTUP_GRACE_SEC", 1.0):
            proc = launcher._run_and_watch(Path(sys.executable), root)
        self.assertFalse(self.died)
        self.assertIsNone(proc.poll())  # 유예 시간을 넘겨 살아 있다
        proc.kill()
        proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
