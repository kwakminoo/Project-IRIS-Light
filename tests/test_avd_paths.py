"""AVD 경로 복구 — 다른 PC에서 clone 해도 에뮬레이터가 뜨게 한다.

저장소에 커밋돼 있던 `IrisLight_Pixel.ini` 에는 만든 사람 PC의 절대경로가
박혀 있었다. 다른 PC에서는 에뮬레이터가 config.ini 를 못 읽고 기본값(arm)으로
떨어져서 이렇게 죽는다:

    CPU Architecture 'arm' is not supported by the QEMU2 emulator

메시지만 봐서는 경로 문제라는 걸 알 수 없다. 실제로 이 저장소를 clone 한
PC에서 에뮬레이터가 부팅되지 않는 것을 확인했다.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest import TestCase, mock

from iris.system import android_emulator as ae

_FOREIGN = r"c:\Users\someone-else\Desktop\Project-IRIS-Light-main\android-emulator\avd"


class _AvdSandbox:
    """AVD_HOME 을 임시 폴더로 갈아끼운다."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.avd_home = root / "avd"
        self.avd_dir = self.avd_home / f"{ae.AVD_NAME}.avd"
        self.pointer = self.avd_home / f"{ae.AVD_NAME}.ini"
        self._patches: list = []

    def __enter__(self) -> "_AvdSandbox":
        self.avd_dir.mkdir(parents=True, exist_ok=True)
        self._patches = [
            mock.patch.object(ae, "AVD_HOME", self.avd_home),
            mock.patch.object(ae, "DATA_DIR", self.root / "data"),
        ]
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc) -> None:
        for patch in reversed(self._patches):
            patch.stop()

    def write_foreign_pointer(self) -> None:
        self.pointer.write_text(
            "avd.ini.encoding=UTF-8\n"
            f"path={_FOREIGN}\\{ae.AVD_NAME}.avd\n"
            "target=android-36\n",
            encoding="utf-8",
        )


class AvdPointerRepairTests(TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = Path(tempfile.mkdtemp(prefix="iris_avd_"))

    def test_foreign_path_is_rewritten(self) -> None:
        with _AvdSandbox(self.tmp) as box:
            box.write_foreign_pointer()
            self.assertTrue(ae.repair_avd_pointer())
            body = box.pointer.read_text(encoding="utf-8")
            self.assertNotIn("someone-else", body)
            self.assertIn(str(box.avd_dir), body)

    def test_missing_pointer_is_created(self) -> None:
        with _AvdSandbox(self.tmp) as box:
            self.assertFalse(box.pointer.exists())
            self.assertTrue(ae.repair_avd_pointer())
            self.assertTrue(box.pointer.is_file())
            self.assertIn(str(box.avd_dir), box.pointer.read_text(encoding="utf-8"))

    def test_repair_is_idempotent(self) -> None:
        """매 기동마다 불리므로, 이미 맞으면 파일을 건드리지 않아야 한다."""
        with _AvdSandbox(self.tmp) as box:
            box.write_foreign_pointer()
            self.assertTrue(ae.repair_avd_pointer())
            self.assertFalse(ae.repair_avd_pointer())

    def test_no_avd_directory_is_a_noop(self) -> None:
        with _AvdSandbox(self.tmp) as box:
            for child in box.avd_dir.iterdir():
                child.unlink()
            box.avd_dir.rmdir()
            self.assertFalse(ae.repair_avd_pointer())

    def test_pointer_target_matches_system_image(self) -> None:
        """포인터의 target 과 실제 시스템 이미지 API 레벨이 어긋나면 안 된다."""
        self.assertIn(ae._AVD_TARGET.replace("android-", ""), ae._SYSTEM_IMAGE)


class ForeignRuntimeArtifactTests(TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = Path(tempfile.mkdtemp(prefix="iris_avd_art_"))

    def test_artifacts_with_foreign_paths_are_dropped(self) -> None:
        """hardware-qemu.ini 등은 기동 때마다 재생성된다.

        커밋돼 있으면 남의 SDK 경로를 물고 들어오므로, 이 PC 것이 아니면 지운다.
        """
        with _AvdSandbox(self.tmp) as box:
            stale = box.avd_dir / "hardware-qemu.ini"
            stale.write_text(
                r"kernel.path = C:\Users\someone-else\AppData\Local\Android\Sdk\x",
                encoding="utf-8",
            )
            dropped = ae._drop_foreign_runtime_artifacts()
            self.assertIn("hardware-qemu.ini", dropped)
            self.assertFalse(stale.exists())

    def test_local_artifacts_are_kept(self) -> None:
        with _AvdSandbox(self.tmp) as box:
            mine = box.avd_dir / "hardware-qemu.ini"
            mine.write_text(f"kernel.path = {ae._sdk_root()}\\x", encoding="utf-8")
            self.assertEqual(ae._drop_foreign_runtime_artifacts(), [])
            self.assertTrue(mine.exists())

    def test_missing_artifacts_are_fine(self) -> None:
        with _AvdSandbox(self.tmp):
            self.assertEqual(ae._drop_foreign_runtime_artifacts(), [])


class GitHygieneTests(TestCase):
    """런타임 산출물이 다시 커밋되지 않도록 .gitignore 를 지킨다."""

    def test_runtime_artifacts_are_ignored(self) -> None:
        root = Path(__file__).resolve().parents[1]
        gitignore = root / ".gitignore"
        if not gitignore.is_file():
            self.skipTest(".gitignore 없음")
        body = gitignore.read_text(encoding="utf-8")
        for pattern in (
            "android-emulator/avd/**/hardware-qemu.ini",
            "android-emulator/avd/**/emulator-user.ini",
            "android-emulator/avd/*.ini",
        ):
            self.assertIn(pattern, body, f"{pattern} 가 .gitignore 에 없다")


class EmulatorNoConsoleWindowTests(TestCase):
    """기동/종료/스캔 시 Windows 콘솔 창이 뜨지 않도록 숨김 kwargs를 쓴다."""

    def test_scan_processes_uses_psutil_not_powershell(self) -> None:
        src = Path(ae.__file__).read_text(encoding="utf-8")
        scan_src = src.split("def _scan_processes", 1)[1].split("def _is_emulator_binary", 1)[0]
        code_lines = [
            ln for ln in scan_src.splitlines() if not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines).lower()
        self.assertIn("psutil", code)
        self.assertNotIn("powershell", code)
        self.assertNotIn("tasklist", code)

    def test_force_kill_passes_no_window_kwargs(self) -> None:
        with mock.patch.object(ae, "_no_window_kwargs", return_value={"creationflags": 0x08000000}):
            with mock.patch("subprocess.run", return_value=mock.Mock()) as run:
                self.assertTrue(ae._force_kill_pid(12345))
        self.assertIn("creationflags", run.call_args.kwargs)

    def test_helper_is_wired_for_launch_and_kill(self) -> None:
        src = Path(ae.__file__).read_text(encoding="utf-8")
        self.assertIn("_no_window_kwargs(", src)
        self.assertIn("CREATE_NEW_PROCESS_GROUP", src)
        self.assertIn("DETACHED_PROCESS", src)
        self.assertIn('_GPU_MODE = "host"', src)
        self.assertIn("_gui_launch_creationflags", src)
        launch_src = src.split("def launch_emulator", 1)[1].split(
            "\ndef restart_emulator", 1
        )[0]
        code_lines = [
            ln for ln in launch_src.splitlines() if not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # GUI 기동 경로에는 CREATE_NO_WINDOW 금지 (검은 화면)
        self.assertNotIn("CREATE_NO_WINDOW", code)
        self.assertNotIn("startupinfo", code.lower())
        self.assertIn("netsimd.exe", src)
        self.assertGreaterEqual(src.count("**_no_window_kwargs()"), 5)
