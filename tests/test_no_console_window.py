"""Regression: Windows subprocess must hide console windows.

CallMonitor/adb/taskkill이 콘솔을 깜빡이면 안 된다.
에뮬 GUI 기동은 DETACHED(+NEW_GROUP)만 — CREATE_NO_WINDOW는
UpdateLayeredWindowIndirect 실패(검은 화면).
Win11 netsimd/qemu 터미널은 Cascadia/PseudoConsole 표면 숨김.
프로세스 스캔은 PowerShell 대신 psutil (콘솔 0).
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path
from unittest import TestCase, mock

from iris.system import android_emulator as ae
from iris.system.phone_control import read_call_state
from iris.system.win_subprocess import no_window_kwargs


class NoWindowKwargsContractTests(TestCase):
    def test_extra_creationflags_merged_on_windows_signature(self) -> None:
        sig = inspect.signature(no_window_kwargs)
        self.assertIn("extra_creationflags", sig.parameters)

    def test_non_windows_or_flags(self) -> None:
        kw = no_window_kwargs(extra_creationflags=0x200)
        if sys.platform == "win32":
            self.assertIn("creationflags", kw)
            self.assertTrue(kw["creationflags"] & 0x200)
            self.assertTrue(
                kw["creationflags"] & int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            )
        else:
            self.assertEqual(kw, {})


class SourceGuardTests(TestCase):
    def test_android_emulator_hides_console_helpers(self) -> None:
        path = Path(ae.__file__)
        body = path.read_text(encoding="utf-8")
        self.assertIn("def _no_window_kwargs", body)
        self.assertIn("def _gui_launch_creationflags", body)
        self.assertIn("netsimd.exe", body)
        self.assertRegex(body, r'_GPU_MODE\s*=\s*"host"')
        self.assertIn("**_no_window_kwargs()", body)
        self.assertIn("psutil", body)
        self.assertIn("CASCADIA_HOSTING_WINDOW_CLASS", body)
        self.assertIn("PseudoConsoleWindow", body)
        self.assertIn("_hide_emulator_console_surfaces", body)
        launch_src = body.split("def launch_emulator", 1)[1].split(
            "\ndef restart_emulator", 1
        )[0]
        code_lines = [
            ln for ln in launch_src.splitlines() if not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        self.assertIn("_gui_launch_creationflags()", code)
        self.assertIn("_schedule_console_hide", code)
        self.assertNotIn("startupinfo", code.lower())
        self.assertNotIn("STARTF_USESHOWWINDOW", code)
        self.assertNotIn("CREATE_NO_WINDOW", code)


class HotPathTests(TestCase):
    def test_capture_output_passes_create_no_window_on_win32(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows only")
        with mock.patch("subprocess.check_output", return_value="") as check:
            ae._capture_output(["adb", "devices"], timeout=1.0)
        kwargs = check.call_args.kwargs
        self.assertEqual(
            kwargs["creationflags"],
            int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )

    def test_gui_launch_flags_exclude_create_no_window(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows only")
        flags = ae._gui_launch_creationflags()
        self.assertFalse(flags & int(getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        self.assertTrue(flags & int(getattr(subprocess, "DETACHED_PROCESS", 0)))
        self.assertIn("netsimd.exe", ae._CONSOLE_HELPER_NAMES)
        self.assertIn("CASCADIA_HOSTING_WINDOW_CLASS", ae._CONSOLE_SURFACE_CLASSES)
        self.assertTrue(ae._is_emulator_console_title(
            r"C:\Users\x\AppData\Local\Android\Sdk\emulator\netsimd.exe"
        ))
        self.assertFalse(ae._is_emulator_console_title(r"C:\Windows\System32\cmd.exe"))

    def test_require_serial_skips_process_scan_when_adb_empty(self) -> None:
        with mock.patch.object(ae, "_matching_emulator_serials", return_value=[]):
            with mock.patch.object(ae, "_running_emulator_serials", return_value=[]):
                with mock.patch.object(ae, "_list_emulator_processes") as scan:
                    with self.assertRaises(ae.AdbError) as ctx:
                        ae.require_serial()
        scan.assert_not_called()
        self.assertIn("미실행", str(ctx.exception))

    def test_read_call_state_does_not_raise_when_offline(self) -> None:
        with mock.patch(
            "iris.system.phone_control.require_serial",
            side_effect=ae.AdbError("에뮬레이터 미실행"),
        ):
            snap = read_call_state()
        self.assertTrue(snap.error)
        self.assertEqual(snap.state.value, "unknown")
