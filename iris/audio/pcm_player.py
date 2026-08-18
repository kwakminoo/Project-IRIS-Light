"""문장 사이 재시작 없이 PCM을 이어 붙이는 재생기."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

from iris.audio.pcm_stream import DEFAULT_SAMPLE_RATE, START_MS, should_open_speakers


class PcmPlayer(QObject):
    speakers_opened = pyqtSignal()
    drained = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, *, start_ms: int = START_MS) -> None:
        super().__init__(parent)
        self._start_ms = int(start_ms)
        self._sr = DEFAULT_SAMPLE_RATE
        self._volume = 1.0
        self._buf = bytearray()
        self._sink: QAudioSink | None = None
        self._io = None
        self._opened = False
        self._ending = False

    def is_open(self) -> bool:
        return self._opened

    def is_busy(self) -> bool:
        return self._opened or bool(self._buf)

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume)))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    def set_format(self, sample_rate: int) -> None:
        rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
        if rate == self._sr:
            return
        had = self.is_busy()
        self.stop()
        self._sr = rate
        if had:
            self.failed.emit("샘플레이트가 바뀌어 재생을 다시 시작합니다.")

    def feed(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._ending = False
        if self._opened:
            self._write(pcm)
            return
        self._buf.extend(pcm)
        if should_open_speakers(len(self._buf), self._sr, stream_ended=False, start_ms=self._start_ms):
            self._open_speakers()

    def flush_start(self) -> None:
        """한 문장 스트림이 끝났을 때 — 버퍼가 짧아도 Speakers를 연다."""
        if self._opened or not self._buf:
            return
        if should_open_speakers(len(self._buf), self._sr, stream_ended=True, start_ms=self._start_ms):
            self._open_speakers()

    def end_session(self) -> None:
        self._ending = True
        self.flush_start()
        if not self._opened:
            self.drained.emit()
            return
        if self._sink is not None and self._sink.state() == QAudio.State.IdleState:
            self.stop()
            self.drained.emit()

    def stop(self) -> None:
        self._buf.clear()
        self._opened = False
        self._ending = False
        io, self._io = self._io, None
        sink, self._sink = self._sink, None
        if io is not None:
            try:
                io.close()
            except Exception:
                pass
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass

    def _open_speakers(self) -> None:
        fmt = QAudioFormat()
        fmt.setSampleRate(self._sr)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self.failed.emit("기본 출력 장치가 없습니다.")
            self._buf.clear()
            return
        try:
            sink = QAudioSink(device, fmt, self)
            # ponytail: 2초치 버퍼. 기본값(~200ms)은 push 모드에서 write가 짤려 무음이 됨.
            sink.setBufferSize(self._sr * 2 * 2)
            sink.setVolume(self._volume)
            sink.stateChanged.connect(self._on_state)
            io = sink.start()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"PCM 재생 시작 실패: {exc}")
            self._buf.clear()
            return
        self._sink = sink
        self._io = io
        self._opened = True
        pending = bytes(self._buf)
        self._buf.clear()
        if pending:
            self._write(pending)
        self.speakers_opened.emit()

    def _write(self, pcm: bytes) -> None:
        io = self._io
        if io is None:
            return
        try:
            view = memoryview(pcm)
            offset = 0
            while offset < len(view):
                n = io.write(bytes(view[offset:]))
                if n <= 0:
                    # 버퍼가 가득 찼으면 남은 분량을 앞에 넣어 다음 feed 때 재시도
                    self._buf[0:0] = view[offset:]
                    break
                offset += n
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"PCM 쓰기 실패: {exc}")

    def _on_state(self, state: object) -> None:
        if state != QAudio.State.IdleState:
            return
        # IdleState: 아직 보낼 데이터가 버퍼에 있으면 먼저 내보냄
        if self._buf and self._opened:
            pending = bytes(self._buf)
            self._buf.clear()
            self._write(pending)
            return
        if not self._ending:
            return
        self.stop()
        self.drained.emit()
