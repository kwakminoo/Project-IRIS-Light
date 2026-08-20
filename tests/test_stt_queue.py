"""STT 큐는 capture를 멈추지 않고 순차 처리한다."""

from __future__ import annotations

import sys
from unittest import TestCase

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from iris.audio.recorder import RecordingResult
from iris.audio.stt_queue import SttJobQueue

_APP = QApplication.instance() or QApplication(sys.argv)


class FakeSttWorker(QObject):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
    started: list["FakeSttWorker"] = []

    def __init__(self, wav_bytes: bytes, **kwargs) -> None:
        super().__init__(kwargs.get("parent"))
        self.wav_bytes = wav_bytes
        self.running = False
        FakeSttWorker.started.append(self)

    def isRunning(self) -> bool:  # noqa: N802
        return self.running

    def start(self) -> None:
        self.running = True

    def complete(self, text: str) -> None:
        self.running = False
        self.finished_ok.emit({"text": text})
        self.finished.emit()


def _result(tag: bytes) -> RecordingResult:
    return RecordingResult(
        wav_bytes=tag,
        rms_peak=0.1,
        duration_sec=1.0,
        sample_rate=16000,
        channels=1,
        speech_start_ts=1.0,
        speech_end_ts=2.0,
        utterance_ready_ts=2.0,
    )


class SttQueueTests(TestCase):
    def setUp(self) -> None:
        FakeSttWorker.started = []
        self.done: list[tuple[object, int]] = []
        self.queue = SttJobQueue(worker_factory=FakeSttWorker)
        self.queue.finished_ok.connect(lambda payload, sid: self.done.append((payload, sid)))

    def test_second_utterance_queues_until_first_finishes(self) -> None:
        self.queue.enqueue(_result(b"A"), session_id=1)
        self.queue.enqueue(_result(b"B"), session_id=1)
        self.assertEqual(len(FakeSttWorker.started), 1)
        self.assertEqual(FakeSttWorker.started[0].wav_bytes, b"A")
        FakeSttWorker.started[0].complete("a")
        self.assertEqual(len(FakeSttWorker.started), 2)
        self.assertEqual(FakeSttWorker.started[1].wav_bytes, b"B")
        FakeSttWorker.started[1].complete("b")
        self.assertEqual([p[0]["text"] for p in self.done], ["a", "b"])
