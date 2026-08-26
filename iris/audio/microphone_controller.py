"""단일 마이크 상태 컨트롤러. UI/설정은 장치를 직접 열지 않는다."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.audio.mic_state import MicState
from iris.audio.recorder import AudioRecorder, RecordingResult


class MicrophoneController(QObject):
    state_changed = pyqtSignal(object)  # MicState
    level_changed = pyqtSignal(float)
    speech_started = pyqtSignal()
    utterance_ready = pyqtSignal(object)  # RecordingResult
    utterance_dropped = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        recorder: AudioRecorder | None = None,
    ) -> None:
        super().__init__(parent)
        self._recorder = recorder or AudioRecorder(self)
        self._state = MicState.OFF
        self._device_id = ""
        self._speech_rms = 0.02
        self._session_id = 0
        self._echo_tail_ms = 180
        self._echo_timer = QTimer(self)
        self._echo_timer.setSingleShot(True)
        self._echo_timer.timeout.connect(self._finish_echo_tail)
        self._switching = False
        self._restore_device_id: str | None = None

        self._recorder.level_changed.connect(self.level_changed.emit)
        self._recorder.recording_started.connect(self._on_started)
        self._recorder.recording_cancelled.connect(self._on_cancelled)
        self._recorder.utterance_ready.connect(self._on_utterance)
        self._recorder.utterance_dropped.connect(self.utterance_dropped.emit)
        self._recorder.speech_started.connect(self._on_speech)
        self._recorder.failed.connect(self._on_failed)

    @property
    def state(self) -> MicState:
        return self._state

    @property
    def session_id(self) -> int:
        return self._session_id

    @property
    def device_id(self) -> str:
        return self._device_id

    def is_hardware_open(self) -> bool:
        return self._recorder.is_hardware_open()

    def request_on(
        self,
        *,
        device_id: str = "",
        speech_rms: float = 0.02,
        stt_enabled: bool = True,
    ) -> None:
        if not stt_enabled:
            self.error.emit("STT가 비활성화되어 있습니다. 설정에서 STT 사용을 켜세요.")
            return
        if self._state.is_hardware_open() and self._state != MicState.STARTING:
            return
        if self._state == MicState.STARTING:
            return
        self._device_id = device_id
        self._speech_rms = speech_rms
        self._echo_timer.stop()
        self._set_state(MicState.STARTING)
        self._recorder.start_continuous(device_id=device_id, speech_rms=speech_rms)

    def request_off(self) -> None:
        self._session_id += 1
        self._echo_timer.stop()
        self._switching = False
        self._restore_device_id = None
        if self._recorder.is_recording():
            self._recorder.cancel_recording()
        else:
            self._set_state(MicState.OFF)

    def set_device(self, device_id: str) -> None:
        device_id = str(device_id or "")
        if device_id == self._device_id and self._state.is_listening_ui():
            return
        prev = self._device_id
        self._device_id = device_id
        if not self._state.is_listening_ui() and self._state != MicState.STARTING:
            return
        self._switching = True
        self._restore_device_id = prev
        self._echo_timer.stop()
        if self._recorder.is_recording():
            self._recorder.cancel_recording()
            return
        self._open_current()

    def set_speech_rms(self, rms: float) -> None:
        self._speech_rms = float(rms)
        self._recorder.set_speech_rms(self._speech_rms)

    def set_echo_source(self, source: object | None) -> None:
        self._recorder.set_echo_source(source)  # type: ignore[arg-type]

    def suppress_speech(
        self,
        on: bool,
        *,
        echo_tail_ms: int | None = None,
        allow_barge_in: bool = True,
    ) -> None:
        if echo_tail_ms is not None:
            self._echo_tail_ms = max(0, int(echo_tail_ms))
        if on:
            self._echo_timer.stop()
            if not self._state.is_listening_ui() and self._state != MicState.STARTING:
                return
            if allow_barge_in:
                self._recorder.set_echo_cancel(True, delay_ms=self._echo_tail_ms)
            else:
                # 끼어들기 OFF — AEC 경로로 듣고 있지 말고 발화 검출만 완전 정지
                self._recorder.set_echo_cancel(False, delay_ms=self._echo_tail_ms)
                self._recorder.set_capture_paused(True)
            if self._recorder.is_capture_paused() and self._state.is_listening_ui():
                self._set_state(MicState.SUSPENDED)
            return
        delay = max(0, self._echo_tail_ms)
        if delay <= 0:
            self._finish_echo_tail()
            return
        self._echo_timer.start(delay)

    def _finish_echo_tail(self) -> None:
        self._recorder.set_echo_cancel(False)
        if self._state == MicState.SUSPENDED:
            self._set_state(MicState.LISTENING)

    def _open_current(self) -> None:
        self._set_state(MicState.STARTING)
        self._recorder.start_continuous(device_id=self._device_id, speech_rms=self._speech_rms)

    def _set_state(self, state: MicState) -> None:
        if self._state == state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _on_started(self) -> None:
        if self._state == MicState.STARTING:
            self._switching = False
            self._restore_device_id = None
            self._set_state(MicState.LISTENING)

    def _on_cancelled(self) -> None:
        if self._switching:
            self._switching = False
            self._open_current()
            return
        self._set_state(MicState.OFF)

    def _on_speech(self) -> None:
        if self._state in (MicState.LISTENING, MicState.SUSPENDED):
            self._set_state(MicState.SPEECH)
        self.speech_started.emit()

    def _on_utterance(self, result: RecordingResult) -> None:
        if self._state == MicState.SPEECH:
            self._set_state(MicState.LISTENING)
        if self._state in (MicState.LISTENING, MicState.SPEECH, MicState.SUSPENDED):
            self.utterance_ready.emit(result)

    def _on_failed(self, err: str) -> None:
        restore = self._restore_device_id
        self._restore_device_id = None
        self._switching = False
        if restore is not None and restore != self._device_id:
            self._device_id = restore
            self._open_current()
            self.error.emit(err)
            return
        self._session_id += 1
        if self._recorder.is_recording():
            self._recorder.cancel_recording()
        self._set_state(MicState.ERROR)
        self.error.emit(err)
        self._set_state(MicState.OFF)
