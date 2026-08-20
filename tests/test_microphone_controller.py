"""MicrophoneController 상태/장치/TTS suppress — QAudioSource 없이 Fake capture."""

from __future__ import annotations

import sys
from unittest import TestCase

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from iris.audio.mic_state import MicState
from iris.audio.microphone_controller import MicrophoneController
from iris.audio.recorder import RecordingResult

_APP = QApplication.instance() or QApplication(sys.argv)


class FakeRecorder(QObject):
    level_changed = pyqtSignal(float)
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(object)
    recording_cancelled = pyqtSignal()
    utterance_ready = pyqtSignal(object)
    speech_started = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.open = False
        self.paused = False
        self.preroll = ["stale"]
        self.start_calls: list[str] = []
        self.fail_next = False
        self.echo_source = None
        self.aec = False
        self.echo_delay_ms = 180

    def is_recording(self) -> bool:
        return self.open

    def is_hardware_open(self) -> bool:
        return self.open

    def is_continuous(self) -> bool:
        return self.open

    def is_capture_paused(self) -> bool:
        return self.paused

    def set_echo_source(self, source: object | None) -> None:
        self.echo_source = source

    def start_continuous(self, *, device_id: str = "", speech_rms: float = 0.02, **_kwargs) -> None:
        del speech_rms
        self.start_calls.append(device_id)
        if self.fail_next:
            self.fail_next = False
            self.failed.emit("open failed")
            return
        self.open = True
        self.recording_started.emit()

    def cancel_recording(self) -> None:
        self.open = False
        self.preroll.clear()
        self.recording_cancelled.emit()

    def set_speech_rms(self, rms: float) -> None:
        del rms

    def set_capture_paused(self, paused: bool) -> None:
        self.paused = bool(paused)
        self.preroll.clear()

    def set_echo_cancel(self, on: bool, *, delay_ms: int = 180) -> None:
        self.echo_delay_ms = delay_ms
        if on and self.echo_source is None:
            self.set_capture_paused(True)
            self.aec = False
            return
        self.paused = False
        self.aec = bool(on)
        if on:
            self.preroll.clear()


class MicrophoneControllerTests(TestCase):
    def setUp(self) -> None:
        self.rec = FakeRecorder()
        self.mic = MicrophoneController(recorder=self.rec)
        self.states: list[MicState] = []
        self.mic.state_changed.connect(self.states.append)

    def test_off_hardware_closed(self) -> None:
        self.assertEqual(self.mic.state, MicState.OFF)
        self.assertFalse(self.mic.is_hardware_open())
        self.assertFalse(self.rec.open)

    def test_on_success_listening(self) -> None:
        self.mic.request_on(device_id="dev-a", stt_enabled=True)
        self.assertEqual(self.mic.state, MicState.LISTENING)
        self.assertTrue(self.rec.open)
        self.assertIn(MicState.STARTING, self.states)
        self.assertIn(MicState.LISTENING, self.states)

    def test_on_fail_stays_off(self) -> None:
        self.rec.fail_next = True
        self.mic.request_on(stt_enabled=True)
        self.assertEqual(self.mic.state, MicState.OFF)
        self.assertFalse(self.rec.open)
        self.assertIn(MicState.ERROR, self.states)

    def test_stt_disabled_does_not_open(self) -> None:
        errors: list[str] = []
        self.mic.error.connect(errors.append)
        self.mic.request_on(stt_enabled=False)
        self.assertEqual(self.mic.state, MicState.OFF)
        self.assertFalse(self.rec.open)
        self.assertTrue(errors)

    def test_settings_subscribe_does_not_open(self) -> None:
        levels: list[float] = []
        self.mic.level_changed.connect(levels.append)
        self.assertFalse(self.rec.open)
        self.rec.level_changed.emit(0.4)
        self.assertEqual(levels, [0.4])
        self.assertEqual(self.mic.state, MicState.OFF)
        self.assertEqual(self.rec.start_calls, [])

    def test_device_change_while_off_does_not_open(self) -> None:
        self.mic.set_device("dev-b")
        self.assertEqual(self.mic.device_id, "dev-b")
        self.assertEqual(self.rec.start_calls, [])
        self.assertFalse(self.rec.open)

    def test_device_change_while_on_reopens(self) -> None:
        self.mic.request_on(device_id="dev-a", stt_enabled=True)
        self.rec.start_calls.clear()
        self.mic.set_device("dev-b")
        self.assertEqual(self.rec.start_calls, ["dev-b"])
        self.assertTrue(self.rec.open)
        self.assertEqual(self.mic.state, MicState.LISTENING)

    def test_tts_suppress_clears_preroll_and_is_not_off(self) -> None:
        self.mic.request_on(stt_enabled=True)
        self.rec.preroll.append("echo")
        self.mic.suppress_speech(True, echo_tail_ms=0)
        self.assertEqual(self.mic.state, MicState.SUSPENDED)
        self.assertTrue(self.rec.open)
        self.assertEqual(self.rec.preroll, [])
        self.mic.suppress_speech(False, echo_tail_ms=0)
        self.assertEqual(self.mic.state, MicState.LISTENING)
        self.assertTrue(self.rec.open)

    def test_tts_with_echo_source_keeps_listening_for_barge_in(self) -> None:
        self.rec.set_echo_source(object())
        self.mic.request_on(stt_enabled=True)
        started: list[int] = []
        self.mic.speech_started.connect(lambda: started.append(1))
        self.mic.suppress_speech(True, echo_tail_ms=0)
        self.assertEqual(self.mic.state, MicState.LISTENING)
        self.assertTrue(self.rec.aec)
        self.assertFalse(self.rec.paused)
        self.rec.speech_started.emit()
        self.assertEqual(self.mic.state, MicState.SPEECH)
        self.assertEqual(started, [1])

    def test_off_bumps_session_so_stale_results_drop(self) -> None:
        self.mic.request_on(stt_enabled=True)
        sid = self.mic.session_id
        self.mic.request_off()
        self.assertNotEqual(self.mic.session_id, sid)
        self.assertEqual(self.mic.state, MicState.OFF)
        self.assertFalse(self.rec.open)

    def test_stale_utterance_not_forwarded_after_off(self) -> None:
        got: list[RecordingResult] = []
        self.mic.utterance_ready.connect(got.append)
        self.mic.request_on(stt_enabled=True)
        self.mic.request_off()
        self.rec.utterance_ready.emit(
            RecordingResult(wav_bytes=b"x", rms_peak=0.1, duration_sec=1.0, sample_rate=16000, channels=1)
        )
        self.assertEqual(got, [])
