from __future__ import annotations

import time
from threading import Event
from types import SimpleNamespace
from unittest import TestCase

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from iris.audio.mic_state import MicState
from iris.ui.window.main_window import MainWindow

_APP = QApplication.instance() or QApplication([])


class _SlowRuntime:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def set_base_url(self, _url: str) -> None:
        pass

    def ensure_started(self, **_kwargs):
        self.entered.set()
        self.release.wait(3)
        return SimpleNamespace(running=True)


class _Host(QObject):
    _on_chat_mic_clicked = MainWindow._on_chat_mic_clicked

    def __init__(self) -> None:
        super().__init__()
        self._voice_runtime = _SlowRuntime()
        self._voice_prefs = SimpleNamespace(
            stt_enabled=True, voice_runtime_url="http://127.0.0.1:18765",
            voice_runtime_mock=True, mic_listen_preferred=False,
        )
        self._mic = SimpleNamespace(state=MicState.OFF)
        self._mic_bootstrap_worker = None
        self._mic_start_requested = False
        self.started = 0
        self.preferred = []
        self.stt_status = []
        self._live_activity = SimpleNamespace(append_instant_line=lambda _msg: None)
        self._status_header = SimpleNamespace(
            set_tts_status=lambda _msg: None,
            set_stt_status=self.stt_status.append,
        )

    def _request_mic_start(self) -> None:
        MainWindow._request_mic_start(self)

    def _on_mic_bootstrap_done(self, result: object) -> None:
        MainWindow._on_mic_bootstrap_done(self, result)

    def _on_mic_bootstrap_failed(self, err: str) -> None:
        MainWindow._on_mic_bootstrap_failed(self, err)

    def _on_mic_bootstrap_finished(self, worker: object) -> None:
        MainWindow._on_mic_bootstrap_finished(self, worker)

    def _set_mic_listen(self, on: bool) -> None:
        MainWindow._set_mic_listen(self, on)

    def _stop_mic_listen(self) -> None:
        self._mic_start_requested = False

    def _start_mic_listen(self) -> None:
        self.started += 1

    def _tts_idle_status(self) -> str:
        return "OFF"

    def _persist_mic_listen_preferred(self, value: bool) -> None:
        self.preferred.append(value)


class MicBootstrapNonblockingTests(TestCase):
    def test_click_returns_while_runtime_starts_then_opens_mic(self) -> None:
        host = _Host()
        try:
            started = time.monotonic()
            host._on_chat_mic_clicked()
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertTrue(host._voice_runtime.entered.wait(1))
            self.assertEqual(host.started, 0)
            self.assertEqual(host.stt_status[-1], "BUSY")
            host._voice_runtime.release.set()
            deadline = time.monotonic() + 2
            while host.started == 0 and time.monotonic() < deadline:
                _APP.processEvents()
                time.sleep(0.01)
            self.assertEqual(host.started, 1)
        finally:
            host._voice_runtime.release.set()
            worker = host._mic_bootstrap_worker
            if worker is not None:
                worker.wait(2000)

    def test_second_click_cancels_pending_mic_start(self) -> None:
        host = _Host()
        try:
            host._on_chat_mic_clicked()
            self.assertTrue(host._voice_runtime.entered.wait(1))
            host._on_chat_mic_clicked()
            self.assertEqual(host.preferred[-1], False)
            self.assertEqual(host.stt_status[-1], "OFF")
            host._voice_runtime.release.set()
            worker = host._mic_bootstrap_worker
            self.assertIsNotNone(worker)
            worker.wait(2000)
            _APP.processEvents()
            self.assertEqual(host.started, 0)
        finally:
            host._voice_runtime.release.set()

    def test_mic_off_command_cancels_pending_start(self) -> None:
        host = _Host()
        try:
            host._on_chat_mic_clicked()
            self.assertTrue(host._voice_runtime.entered.wait(1))
            host._set_mic_listen(False)
            host._voice_runtime.release.set()
            worker = host._mic_bootstrap_worker
            self.assertIsNotNone(worker)
            worker.wait(2000)
            _APP.processEvents()
            self.assertEqual(host.started, 0)
            self.assertEqual(host.preferred[-1], False)
        finally:
            host._voice_runtime.release.set()

    def test_click_again_after_cancelling_restarts_mic(self) -> None:
        host = _Host()
        try:
            host._on_chat_mic_clicked()
            self.assertTrue(host._voice_runtime.entered.wait(1))
            host._on_chat_mic_clicked()
            host._on_chat_mic_clicked()
            host._voice_runtime.release.set()
            deadline = time.monotonic() + 2
            while host.started == 0 and time.monotonic() < deadline:
                _APP.processEvents()
                time.sleep(0.01)
            self.assertEqual(host.started, 1)
        finally:
            host._voice_runtime.release.set()
            worker = host._mic_bootstrap_worker
            if worker is not None:
                worker.wait(2000)
