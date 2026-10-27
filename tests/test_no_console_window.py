"""Regression: Windows subprocess must hide console windows.

CallMonitor/adb/taskkill이 콘솔을 깜빡이면 안 된다.
채팅 전송(텍스트·이미지)도 Cascadia/콘솔 플래시 금지.
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
from iris.system.hermes_iris_control_sync import _python_cmd, project_root
from iris.system.phone_control import read_call_state
from iris.system.win_subprocess import (
    harden_subprocess_kwargs,
    install_no_console_subprocess_patch,
    no_window_kwargs,
    suppress_platform_ver_console,
)


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

    def test_harden_injects_create_no_window(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows only")
        kw = harden_subprocess_kwargs({})
        self.assertTrue(
            kw["creationflags"] & int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        )
        self.assertIn("startupinfo", kw)

    def test_harden_skips_detached_gui_launch(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows only")
        detached = int(getattr(subprocess, "DETACHED_PROCESS", 0))
        kw = harden_subprocess_kwargs({"creationflags": detached})
        self.assertEqual(kw["creationflags"], detached)
        self.assertNotIn("startupinfo", kw)

    def test_iris_main_installs_no_console_guards(self) -> None:
        body = Path(__file__).resolve().parents[1] / "iris" / "__main__.py"
        text = body.read_text(encoding="utf-8")
        self.assertIn("suppress_platform_ver_console", text)
        self.assertIn("install_no_console_subprocess_patch", text)

    def test_mcp_python_prefers_pythonw_on_windows(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows only")
        root = project_root()
        win_w = root / ".venv" / "Scripts" / "pythonw.exe"
        if not win_w.is_file():
            self.skipTest("project .venv pythonw missing")
        cmd = _python_cmd(root)
        self.assertTrue(cmd.lower().endswith("pythonw.exe"), cmd)

    def test_suppress_platform_ver_is_idempotent(self) -> None:
        suppress_platform_ver_console()
        suppress_platform_ver_console()
        if sys.platform == "win32":
            import platform

            self.assertTrue(getattr(platform, "_iris_syscmd_ver_suppressed", False))

    def test_install_patch_is_idempotent(self) -> None:
        first = install_no_console_subprocess_patch()
        second = install_no_console_subprocess_patch()
        if sys.platform == "win32":
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertTrue(getattr(subprocess, "_iris_no_console_patched", False))
        else:
            self.assertFalse(first)
            self.assertFalse(second)

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


class AttachmentConsoleGuardTests(TestCase):
    def test_media_preview_does_not_launch_opencv(self) -> None:
        body = (
            Path(__file__).resolve().parents[1]
            / "iris"
            / "ui"
            / "chat"
            / "composer_attachments.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import cv2", body)
        self.assertIn("def _shell_thumbnail", body)

    def test_tesseract_spawn_uses_no_window(self) -> None:
        body = (
            Path(__file__).resolve().parents[1]
            / "iris"
            / "knowledge"
            / "content_extract.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _hide_tesseract_console", body)
        self.assertIn("no_window_kwargs()", body)

    def test_ide_bridge_git_uses_windows_hide(self) -> None:
        root = Path(__file__).resolve().parents[1]
        standalone = (
            root / "integrations" / "iris-ide" / "bridge" / "standalone-bridge.js"
        ).read_text(encoding="utf-8")
        server = (
            root
            / "integrations"
            / "iris-ide"
            / "src"
            / "node"
            / "iris-ide-bridge-server.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("windowsHide: true", standalone)
        self.assertIn("windowsHide: true", server)
        self.assertIn("git status --porcelain", standalone)
        self.assertIn("git status --porcelain", server)


class VoiceRuntimeGuardTests(TestCase):
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
