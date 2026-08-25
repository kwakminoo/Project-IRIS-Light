"""Regression: Windows subprocess must hide console windows.

에뮬레이터 기동/종료·음성 런타임 기동에서 powershell/taskkill/adb/python이
콘솔 창을 띄우면 안 된다. CREATE_NO_WINDOW / no_window_kwargs 사용을 고정한다.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest import TestCase

from iris.system.win_subprocess import no_window_kwargs


class NoWindowKwargsContractTests(TestCase):
    def test_extra_creationflags_merged_on_windows_signature(self) -> None:
        sig = inspect.signature(no_window_kwargs)
        self.assertIn("extra_creationflags", sig.parameters)

    def test_non_windows_returns_empty(self) -> None:
        # 리눅스 CI에서는 빈 dict. Windows에서는 CREATE_NO_WINDOW 포함.
        import sys

        kw = no_window_kwargs(extra_creationflags=0x200)
        if sys.platform == "win32":
            self.assertIn("creationflags", kw)
            self.assertTrue(kw["creationflags"] & 0x200)
        else:
            self.assertEqual(kw, {})


class SourceGuardTests(TestCase):
    def test_android_emulator_hides_console_helpers(self) -> None:
        path = Path(__file__).resolve().parents[1] / "iris" / "system" / "android_emulator.py"
        body = path.read_text(encoding="utf-8")
        for needle in (
            "def _no_window_kwargs",
            "CREATE_NEW_PROCESS_GROUP",
            "**_no_window_kwargs()",
        ):
            self.assertIn(needle, body)

    def test_voice_runtime_manager_resolves_cross_platform_venv(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "iris"
            / "audio"
            / "voice_runtime_manager.py"
        )
        body = path.read_text(encoding="utf-8")
        self.assertIn('Scripts" / "python.exe"', body)
        self.assertIn('bin" / "python"', body)
        self.assertIn("_bootstrap_venv", body)
        self.assertIn("_resolve_python", body)
        self.assertIn("_no_window_kwargs()", body)
