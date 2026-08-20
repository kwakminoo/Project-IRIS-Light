from __future__ import annotations

import io
import time
import wave
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QIODevice, QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices

from iris.audio.aec import EchoSource, NlmsAec
from iris.audio.mic_level import rms_to_display_level
from iris.audio.pcm_convert import (
    CANONICAL_RATE,
    rms_int16,
    to_canonical_pcm,
)
from iris.audio.silero_vad import SileroVad
from iris.audio.speech_gate import SpeechGate


@dataclass(frozen=True)
class RecordingResult:
    wav_bytes: bytes
    rms_peak: float
    duration_sec: float
    sample_rate: int
    channels: int
    speech_start_ts: float = 0.0
    speech_end_ts: float = 0.0
    utterance_ready_ts: float = 0.0


_FORMAT_MAP = {
    QAudioFormat.SampleFormat.Int16: "int16",
    QAudioFormat.SampleFormat.Float: "float32",
    QAudioFormat.SampleFormat.Int32: "int32",
    QAudioFormat.SampleFormat.UInt8: "uint8",
}


class AudioRecorder(QObject):
    """가벼운 마이크 캡처 전용. 모델 추론은 별도 워커에서 처리."""

    level_changed = pyqtSignal(float)  # 0..1 display level
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(object)  # RecordingResult
    recording_cancelled = pyqtSignal()
    utterance_ready = pyqtSignal(object)  # RecordingResult (continuous)
    speech_started = pyqtSignal()
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
        self._native_rate = CANONICAL_RATE
        self._native_channels = 1
        self._native_format = "int16"
        self._rms_peak = 0.0
        # ponytail: 너무 짧은 단어/호흡만 말해도 start만 찍히고 drop되는 케이스 완화
        self._gate = SpeechGate(min_speech_frames=3)
        self._vad: SileroVad | None = None
        self._utterance = bytearray()
        self._preroll: deque[bytes] = deque()
        self._preroll_bytes = 0
        self._preroll_limit = int(0.3 * CANONICAL_RATE * 2)  # 300ms
        self._capture_paused = False
        self._speech_start_ts = 0.0
        self._max_utterance_bytes = int(12 * CANONICAL_RATE * 2)
        self._echo_source: EchoSource | None = None
        self._aec = NlmsAec()
        self._aec_enabled = False
        self._echo_delay_ms = 180
        self._aec_holdoff_until = 0.0

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

    def is_hardware_open(self) -> bool:
        return self._audio_source is not None and self._recording

    def is_continuous(self) -> bool:
        return self._mode == "continuous" and self._recording

    def is_monitoring(self) -> bool:
        return self._mode == "monitor" and self._recording

    def _reset_vad(self) -> None:
        if self._vad is not None:
            self._vad.reset()

    def set_speech_rms(self, rms: float) -> None:
        self._gate.set_speech_rms(rms)

    def set_echo_source(self, source: EchoSource | None) -> None:
        self._echo_source = source

    def is_capture_paused(self) -> bool:
        return self._capture_paused

    def set_capture_paused(self, paused: bool) -> None:
        """TTS 중 발화 검출만 멈춤. 장치는 열고 레벨은 유지. preroll에 쌓지 않는다."""
        self._capture_paused = bool(paused)
        self._gate.reset()
        self._reset_vad()
        self._utterance = bytearray()
        self._clear_preroll()

    def set_echo_cancel(self, on: bool, *, delay_ms: int = 180) -> None:
        """TTS far-end가 있으면 AEC+barge-in, 없으면 기존처럼 검출만 멈춘다."""
        self._echo_delay_ms = max(0, int(delay_ms))
        if on:
            if self._echo_source is None:
                self.set_capture_paused(True)
                self._aec_enabled = False
                return
            self._capture_paused = False
            self._aec_enabled = True
            self._aec.reset()
            self._aec_holdoff_until = time.perf_counter() + 0.25
            self._gate.reset()
            self._reset_vad()
            self._utterance = bytearray()
            self._clear_preroll()
            return
        self._aec_enabled = False
        if self._capture_paused:
            self.set_capture_paused(False)

    def start_recording(self, *, device_id: str = "", sample_rate: int = 16000, channels: int = 1) -> None:
        del sample_rate, channels
        self._start(mode="oneshot", device_id=device_id)

    def start_continuous(
        self,
        *,
        device_id: str = "",
        speech_rms: float = 0.02,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        del sample_rate, channels
        self._gate.set_speech_rms(speech_rms)
        self._gate.reset()
        if self._vad is None:
            self._vad = SileroVad()
        else:
            self._vad.reset()
        self._utterance = bytearray()
        self._clear_preroll()
        self._capture_paused = False
        self._start(mode="continuous", device_id=device_id)

    def start_monitor(self, *, device_id: str = "", sample_rate: int = 16000, channels: int = 1) -> None:
        del sample_rate, channels
        self._start(mode="monitor", device_id=device_id)

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
                sample_rate=CANONICAL_RATE,
                channels=1,
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
        self._clear_preroll()
        self._gate.reset()
        self._reset_vad()
        self.recording_cancelled.emit()

    def stop_monitor(self) -> None:
        """설정 게이지용 — 시그널 없이 모니터만 종료."""
        if not self._recording:
            return
        self._close_device()
        self._chunks = bytearray()

    def _start(self, *, mode: str, device_id: str) -> None:
        if self._recording:
            return
        self._chunks = bytearray()
        self._native_rate = CANONICAL_RATE
        self._native_channels = 1
        self._native_format = "int16"
        self._rms_peak = 0.0
        self._mode = mode

        wanted = QAudioFormat()
        wanted.setSampleRate(CANONICAL_RATE)
        wanted.setChannelCount(1)
        wanted.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioInput()
        for dev in QMediaDevices.audioInputs():
            try:
                current_id = bytes(dev.id()).decode("utf-8", errors="ignore")
            except Exception:
                current_id = dev.description()
            if device_id and current_id == device_id:
                device = dev
                break

        fmt = wanted
        if not device.isFormatSupported(wanted):
            # ponytail: native 포맷으로 열고 폴링에서 16k mono int16으로 변환
            fmt = device.preferredFormat()

        self._native_rate = max(1, int(fmt.sampleRate() or CANONICAL_RATE))
        self._native_channels = max(1, int(fmt.channelCount() or 1))
        self._native_format = _FORMAT_MAP.get(fmt.sampleFormat(), "int16")

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
        try:
            err = source.error()
            if err != QAudio.Error.NoError:
                source.stop()
                self._mode = "off"
                self.failed.emit(f"마이크 장치를 열 수 없습니다 ({err}).")
                return
        except Exception:
            pass

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
        self._capture_paused = False
        self._aec_enabled = False
        self._aec.reset()

    def _poll_audio(self) -> None:
        if self._device is None:
            return
        available = self._device.bytesAvailable()
        if available <= 0:
            return
        raw = self._device.read(available)
        if not raw:
            return
        pcm = to_canonical_pcm(
            bytes(raw),
            sample_rate=self._native_rate,
            channels=self._native_channels,
            sample_format=self._native_format,
        )
        if not pcm:
            return
        raw_level = rms_int16(pcm)
        self.level_changed.emit(rms_to_display_level(raw_level))
        level = raw_level
        if not (self._aec_enabled and self._echo_source is not None):
            self._rms_peak = max(self._rms_peak, raw_level)

        if self._mode == "monitor":
            return
        if self._mode == "oneshot":
            self._chunks.extend(pcm)
            return
        if self._mode != "continuous":
            return

        if self._capture_paused:
            return

        if self._aec_enabled and self._echo_source is not None:
            far = self._echo_source.farend_canonical(len(pcm), self._echo_delay_ms)
            pcm = self._aec.process_int16(pcm, far)
            level = rms_int16(pcm)
            self._rms_peak = max(self._rms_peak, level)
            if time.perf_counter() < self._aec_holdoff_until:
                self._push_preroll(pcm)
                return

        vad_prob = (
            self._vad.speech_prob(pcm) if self._vad is not None and self._vad.available else None
        )
        event = self._gate.feed(level, vad_prob)
        if not self._gate.speaking and event != "start":
            self._push_preroll(pcm)
            return
        if event == "start":
            self._utterance = bytearray()
            for pre in self._preroll:
                self._utterance.extend(pre)
            self._clear_preroll()
            self._utterance.extend(pcm)
            self._rms_peak = level
            self._speech_start_ts = time.perf_counter()
            self.speech_started.emit()
            return
        if event == "drop":
            self._utterance = bytearray()
            self._clear_preroll()
            return
        self._utterance.extend(pcm)
        if len(self._utterance) >= self._max_utterance_bytes:
            self._emit_utterance()
            return
        if event == "end":
            self._emit_utterance()

    def _push_preroll(self, data: bytes) -> None:
        self._preroll.append(data)
        self._preroll_bytes += len(data)
        while self._preroll_bytes > self._preroll_limit and self._preroll:
            dropped = self._preroll.popleft()
            self._preroll_bytes -= len(dropped)

    def _clear_preroll(self) -> None:
        self._preroll.clear()
        self._preroll_bytes = 0

    def _emit_utterance(self) -> None:
        pcm = bytes(self._utterance)
        self._utterance = bytearray()
        speech_end = time.perf_counter()
        self._gate.clear_speech()
        self._reset_vad()
        if not pcm:
            return
        now = time.perf_counter()
        result = RecordingResult(
            wav_bytes=self._build_wav_bytes(pcm),
            rms_peak=self._rms_peak,
            duration_sec=self._duration_sec(len(pcm)),
            sample_rate=CANONICAL_RATE,
            channels=1,
            speech_start_ts=self._speech_start_ts or now,
            speech_end_ts=speech_end,
            utterance_ready_ts=now,
        )
        self._rms_peak = 0.0
        self._speech_start_ts = 0.0
        self.utterance_ready.emit(result)

    def _build_wav_bytes(self, pcm_bytes: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(CANONICAL_RATE)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    def _duration_sec(self, nbytes: int | None = None) -> float:
        n = len(self._chunks) if nbytes is None else nbytes
        frames = n / 2.0
        return frames / float(CANONICAL_RATE)
