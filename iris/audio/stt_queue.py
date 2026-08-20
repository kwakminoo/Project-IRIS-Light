"""Capture와 분리된 순차 STT 작업 큐."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.recorder import RecordingResult
from iris.audio.workers import STTTranscriptionWorker

LOGGER = logging.getLogger(__name__)

MAX_PENDING = 3


@dataclass
class SttJob:
    result: RecordingResult
    session_id: int
    queued_at: float = field(default_factory=time.perf_counter)


class SttJobQueue(QObject):
    finished_ok = pyqtSignal(object, int)  # payload, session_id
    failed = pyqtSignal(str, int)
    perf = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        runtime_url: str = "",
        model_name: str = "small",
        language: str = "ko",
        worker_factory=None,
    ) -> None:
        super().__init__(parent)
        self.runtime_url = runtime_url
        self.model_name = model_name
        self.language = language
        self._worker_factory = worker_factory or STTTranscriptionWorker
        self._pending: deque[SttJob] = deque()
        self._worker: STTTranscriptionWorker | None = None
        self._active: SttJob | None = None
        self._request_started_at = 0.0

    def enqueue(self, result: RecordingResult, *, session_id: int) -> None:
        job = SttJob(result=result, session_id=session_id)
        self._pending.append(job)
        while len(self._pending) > MAX_PENDING:
            self._pending.popleft()
        self._kick()

    def clear_pending(self) -> None:
        self._pending.clear()

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _kick(self) -> None:
        if self.is_busy() or not self._pending:
            return
        job = self._pending.popleft()
        self._active = job
        self._request_started_at = time.perf_counter()
        worker = self._worker_factory(
            job.result.wav_bytes,
            runtime_url=self.runtime_url,
            model_name=self.model_name,
            language=self.language,
            parent=self,
        )
        self._worker = worker
        sid = job.session_id
        worker.finished_ok.connect(lambda payload, s=sid: self._on_ok(payload, s))
        worker.failed.connect(lambda err, s=sid: self._on_fail(err, s))
        worker.finished.connect(self._on_thread_finished)
        worker.start()

    def _on_ok(self, payload: object, session_id: int) -> None:
        self._log_perf(payload if isinstance(payload, dict) else {})
        self.finished_ok.emit(payload, session_id)
        self._worker = None
        self._active = None
        self._kick()

    def _on_fail(self, err: str, session_id: int) -> None:
        self.failed.emit(err, session_id)
        self._worker = None
        self._active = None
        self._kick()

    def _on_thread_finished(self) -> None:
        if self._worker is not None and not self._worker.isRunning():
            self._worker = None
            if self._active is not None:
                self._active = None
                self._kick()

    def _log_perf(self, payload: dict) -> None:
        job = self._active
        now = time.perf_counter()
        speech_duration = 0.0
        queue_wait = 0.0
        total_after = 0.0
        if job is not None:
            rec = job.result
            if rec.speech_end_ts and rec.speech_start_ts:
                speech_duration = max(0.0, rec.speech_end_ts - rec.speech_start_ts)
            queue_wait = max(0.0, self._request_started_at - rec.utterance_ready_ts) if rec.utterance_ready_ts else 0.0
            total_after = max(0.0, now - rec.speech_end_ts) if rec.speech_end_ts else 0.0
        upload = float(payload.get("upload_sec") or 0.0)
        transcribe = float(payload.get("transcribe_sec") or 0.0)
        line = (
            "[STT PERF] "
            f"speech_duration={speech_duration:.2f}s "
            f"queue_wait={queue_wait:.2f}s "
            f"upload={upload:.2f}s "
            f"transcribe={transcribe:.2f}s "
            f"total_after_speech={total_after:.2f}s"
        )
        LOGGER.info(line)
        self.perf.emit(line)
