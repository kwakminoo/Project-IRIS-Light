"""Windows에서 실제 입력 장치를 연다. 장치가 없으면 skip."""

from __future__ import annotations

import sys
import time
from unittest import TestCase

from PyQt6.QtWidgets import QApplication

from iris.audio.recorder import AudioRecorder

_APP = QApplication.instance() or QApplication(sys.argv)


class WindowsMicDeviceTests(TestCase):
    def test_open_default_input_device(self) -> None:
        devices = AudioRecorder.list_input_devices()
        if not devices:
            self.skipTest("오디오 입력 장치가 없습니다")
        rec = AudioRecorder()
        levels: list[float] = []
        rec.level_changed.connect(levels.append)
        rec.start_monitor(device_id=devices[0][0])
        deadline = time.perf_counter() + 2.5
        while time.perf_counter() < deadline and not rec.is_hardware_open():
            QApplication.processEvents()
            time.sleep(0.03)
        opened = rec.is_hardware_open()
        if opened:
            drain_until = time.perf_counter() + 0.4
            while time.perf_counter() < drain_until:
                QApplication.processEvents()
                time.sleep(0.03)
        rec.stop_monitor()
        QApplication.processEvents()
        self.assertTrue(opened, f"마이크를 열지 못함: {devices[0]}")
        self.assertFalse(rec.is_hardware_open())
