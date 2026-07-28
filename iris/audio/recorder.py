from __future__ import annotations

import io
import math
import wave
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QIODevice, QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

from iris.audio.mic_level import rms_to_display_level
from iris.audio.speech_gate import SpeechGate


@dataclass(frozen=True)
class RecordingResult:
    wav_bytes: bytes
    rms_peak: float
    duration_sec: float
    sample_rate: int
    channels: int


class AudioRecorder(QObject):
    """가벼운 마이크 캡처 전용. 모델 추론은 별도 워커에서 처리."""

    level_changed = pyqtSignal(float)  # 0..1 display level
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(object)  # RecordingResult
    recording_cancelled = pyqtSignal()
    utterance_ready = pyqtSignal(object)  # RecordingResult (continuous)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio_source: QAudioSource | None = None
        self._device: QIODevice | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_audio)
        self._chunks = bytearray()
        self._recording = False
        self._mode = "off"  # off | oneshot | continuous | monitor
        self._sample_rate = 16000
        self._channels = 1
        self._rms_peak = 0.0
        self._gate = SpeechGate()
        self._utterance = bytearray()
        self._preroll: deque[bytes] = deque(maxlen=12)  # ~600ms
        self._capture_paused = False

    @staticmethod
    def list_input_devices() -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for dev in QMediaDevices.audioInputs():
            try:
                out.append((bytes(dev.id()).decode("utf-8", errors="ignore"), dev.description()))
            except Exception:
                out.append((dev.description(), dev.description()))
        return out

    @staticmethod
    def default_input_label() -> str:
        try:
            return QMediaDevices.defaultAudioInput().description() or "기본 장치"
        except Exception:
            return "기본 장치"

    def is_recording(self) -> bool:
        return self._recording

    def is_continuous(self) -> bool:
        return self._mode == "continuous" and self._recording

    def is_monitoring(self) -> bool:
        return self._mode == "monitor" and self._recording

    def set_speech_rms(self, rms: float) -> None:
        self._gate.set_speech_rms(rms)

    def set_capture_paused(self, paused: bool) -> None:
        """TTS/STT 중 발화 수집만 잠시 멈춤 (레벨 표시는 유지)."""
        self._capture_paused = bool(paused)
        if paused:
            self._gate.reset()
            self._utterance = bytearray()

    def start_recording(self, *, device_id: str = "", sample_rate: int = 16000, channels: int = 1) -> None:
        self._start(mode="oneshot", device_id=device_id, sample_rate=sample_rate, channels=channels)

    def start_continuous(
        self,
        *,
        device_id: str = "",
        speech_rms: float = 0.02,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self._gate.set_speech_rms(speech_rms)
        self._gate.reset()
        self._utterance = bytearray()
        self._preroll.clear()
        self._capture_paused = False
        self._start(mode="continuous", device_id=device_id, sample_rate=sample_rate, channels=channels)

    def start_monitor(self, *, device_id: str = "", sample_rate: int = 16000, channels: int = 1) -> None:
        self._start(mode="monitor", device_id=device_id, sample_rate=sample_rate, channels=channels)

    def stop_recording(self) -> None:
        if not self._recording:
            return
        mode = self._mode
        self._poll_audio()
        self._close_device()
        if mode == "oneshot":
            result = RecordingResult(
                wav_bytes=self._build_wav_bytes(bytes(self._chunks)),
                rms_peak=self._rms_peak,
                duration_sec=self._duration_sec(len(self._chunks)),
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            self.recording_stopped.emit(result)
        elif mode == "continuous" and self._utterance:
            self._emit_utterance()

    def cancel_recording(self) -> None:
        if not self._recording:
            return
        self._close_device()
        self._chunks = bytearray()
        self._utterance = bytearray()
        self._gate.reset()
        self.recording_cancelled.emit()

    def stop_monitor(self) -> None:
        """설정 게이지용 — 시그널 없이 모니터만 종료."""
        if not self._recording:
            return
        self._close_device()
        self._chunks = bytearray()

    def _start(self, *, mode: str, device_id: str, sample_rate: int, channels: int) -> None:
        if self._recording:
            return
        self._chunks = bytearray()
        self._sample_rate = sample_rate
        self._channels = channels
        self._rms_peak = 0.0
        self._mode = mode

        fmt = QAudioFormat()
        fmt.setSampleRate(sample_rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioInput()
        for dev in QMediaDevices.audioInputs():
            try:
                current_id = bytes(dev.id()).decode("utf-8", errors="ignore")
            except Exception:
                current_id = dev.description()
            if device_id and current_id == device_id:
                device = dev
                break

        if not device.isFormatSupported(fmt):
            # ponytail: 먼저 가장 단순한 16k mono int16을 시도하고, 안 되면 preferred 포맷으로 폴백
            fmt = device.preferredFormat()
            self._sample_rate = fmt.sampleRate()
            self._channels = fmt.channelCount()

        try:
            source = QAudioSource(device, fmt, self)
            qdevice = source.start()
        except Exception as exc:  # noqa: BLE001
            self._mode = "off"
            self.failed.emit(f"마이크 시작 실패: {exc}")
            return
        if qdevice is None:
            self._mode = "off"
            self.failed.emit("마이크 장치를 열 수 없습니다.")
            return

        self._audio_source = source
        self._device = qdevice
        self._recording = True
        self._poll_timer.start()
        self.recording_started.emit()

    def _close_device(self) -> None:
        if self._audio_source is not None:
            self._audio_source.stop()
        self._poll_timer.stop()
        self._recording = False
        self._mode = "off"
        self._audio_source = None
        self._device = None

    def _poll_audio(self) -> None:
        if self._device is None:
            return
        available = self._device.bytesAvailable()
        if available <= 0:
            return
        raw = self._device.read(available)
        if not raw:
            return
        data = bytes(raw)
        level = self._compute_rms_level(data)
        self._rms_peak = max(self._rms_peak, level)
        self.level_changed.emit(rms_to_display_level(level))

        if self._mode == "monitor":
            return
        if self._mode == "oneshot":
            self._chunks.extend(data)
            return
        if self._mode != "continuous":
            return

        if self._capture_paused:
            self._preroll.append(data)
            return

        event = self._gate.feed(level)
        if not self._gate.speaking and event != "start":
            self._preroll.append(data)
            return
        if event == "start":
            self._utterance = bytearray()
            for pre in self._preroll:
                self._utterance.extend(pre)
            self._preroll.clear()
            self._utterance.extend(data)
            self._rms_peak = level
            return
        self._utterance.extend(data)
        if event == "end":
            self._emit_utterance()

    def _emit_utterance(self) -> None:
        pcm = bytes(self._utterance)
        self._utterance = bytearray()
        self._gate.reset()
        if not pcm:
            return
        result = RecordingResult(
            wav_bytes=self._build_wav_bytes(pcm),
            rms_peak=self._rms_peak,
            duration_sec=self._duration_sec(len(pcm)),
            sample_rate=self._sample_rate,
            channels=self._channels,
        )
        self._rms_peak = 0.0
        self.utterance_ready.emit(result)

    def _compute_rms_level(self, data: bytes) -> float:
        if not data:
            return 0.0
        import array

        arr = array.array("h")
        usable = len(data) - (len(data) % 2)
        arr.frombytes(data[:usable])
        if not arr:
            return 0.0
        rms = math.sqrt(sum((v / 32768.0) ** 2 for v in arr) / len(arr))
        return float(rms)

    def _build_wav_bytes(self, pcm_bytes: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    def _duration_sec(self, nbytes: int | None = None) -> float:
        sample_width = 2
        n = len(self._chunks) if nbytes is None else nbytes
        frames = n / float(max(1, self._channels * sample_width))
        return frames / float(max(1, self._sample_rate))
