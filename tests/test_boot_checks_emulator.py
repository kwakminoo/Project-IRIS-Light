"""BootChecksWorker — 에뮬 우선 + prepare + 이메일 타임아웃."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest import TestCase, mock

from iris.system import android_emulator as ae
from iris.ui.workers import boot_checks_worker as bc


class PrepareEmulatorTests(TestCase):
    def test_prepare_repairs_before_ok(self) -> None:
        with mock.patch.object(ae, "emulator_exe", return_value=Path("emu.exe")):
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch.object(ae, "adb_exe", return_value=Path("adb.exe")):
                    with mock.patch.object(ae, "_ensure_emulator_disk_space"):
                        with mock.patch.object(
                            ae, "avd_config_path", return_value=Path("cfg.ini")
                        ):
                            with mock.patch.object(
                                ae, "system_image_dir", return_value=Path("img")
                            ):
                                with mock.patch.object(Path, "is_dir", return_value=True):
                                    with mock.patch.object(
                                        ae, "repair_avd_pointer", return_value=True
                                    ) as repair:
                                        with mock.patch.object(
                                            ae,
                                            "_drop_foreign_runtime_artifacts",
                                            return_value=["hardware-qemu.ini"],
                                        ):
                                            with mock.patch.object(ae, "_patch_avd_storage"):
                                                with mock.patch.object(
                                                    ae, "_warm_adb_server"
                                                ) as warm:
                                                    ok, detail = ae.prepare_emulator()
        self.assertTrue(ok)
        self.assertIn("실행 가능", detail)
        self.assertIn("경로 복구", detail)
        repair.assert_called_once()
        warm.assert_called_once()

    def test_is_emulator_available_delegates_to_prepare(self) -> None:
        with mock.patch.object(
            ae, "prepare_emulator", return_value=(True, "실행 가능")
        ) as prep:
            self.assertEqual(ae.is_emulator_available(), (True, "실행 가능"))
        prep.assert_called_once()


class BootChecksOrderTests(TestCase):
    def test_run_checks_emulator_before_email(self) -> None:
        src = Path(bc.__file__).read_text(encoding="utf-8")
        run_src = src.split("def run(self)", 1)[1].split("def _check_emulator", 1)[0]
        self.assertLess(
            run_src.index("_check_emulator"),
            run_src.index("_check_wiki"),
        )
        self.assertLess(
            run_src.index("_check_wiki"),
            run_src.index("_check_email"),
        )

    def test_emulator_check_uses_prepare(self) -> None:
        src = inspect.getsource(bc.BootChecksWorker._check_emulator)
        self.assertIn("prepare_emulator", src)

    def test_email_check_has_timeout(self) -> None:
        src = inspect.getsource(bc.BootChecksWorker._check_email)
        self.assertIn("ThreadPoolExecutor", src)
        self.assertIn("timeout", src)
