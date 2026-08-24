"""알림·전화 낭독 전용 TTS — 채팅 TTS와 분리된 저지연 경로.

채팅 TTS는 스트리밍 응답을 문장 단위로 잘라(TtsSentencePump) 순서대로 재생하는
상태 기계다. 알림은 성격이 정반대다.

  - 문장이 **하나**고 이미 완성돼 있다 → 문장 펌프가 필요 없다
  - **늦으면 의미가 없다** → 전화벨은 몇 초면 끊긴다
  - **최신 것이 이긴다** → 알림 두 개가 겹치면 큐에 쌓지 말고 새 걸로 갈아탄다

그래서 채팅 상태 기계에 끼워 넣지 않고 별도 PcmPlayer 를 쓴다. 채팅 TTS가
말하는 중이어도 알림은 자기 경로로 바로 나간다.

지연을 줄이는 수단:
  1. 지터 버퍼를 최소(MIN_START_MS)로 — 첫 PCM 이 오면 바로 스피커를 연다
  2. 문장 분할·톤 라우팅 왕복 없이 곧장 합성 요청
  3. 앱 시작 때 런타임을 예열해 첫 알림이 콜드 스타트를 맞지 않게 한다
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from iris.audio.pcm_player import PcmPlayer
from iris.audio.pcm_stream import MIN_START_MS
from iris.audio.workers import TTSStreamWorker

# 알림은 짧아야 한다. 길면 사용자가 다 듣기 전에 상황이 끝난다.
MAX_ALERT_CHARS = 160


class AlertPriority:
    """겹쳤을 때 누가 이기는지. 숫자가 클수록 우선."""

    NOTICE = 10
    CALL = 100


class AlertSpeaker(QObject):
    """알림 한 줄을 즉시 읽는다. 겹치면 우선순위가 높은 쪽이 이긴다."""

    started = pyqtSignal(str)   # 낭독 시작한 텍스트
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        runtime_url_provider: Callable[[], str],
        payload_provider: Callable[[], dict],
        volume_provider: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url_provider
        self._payload = payload_provider
        self._volume = volume_provider or (lambda: 1.0)

        # 알림 전용 재생기 — 지터 버퍼를 최소로 잡아 첫 소리를 앞당긴다
        self._player = PcmPlayer(self, start_ms=MIN_START_MS)
        self._player.drained.connect(self._on_drained)
        self._player.failed.connect(lambda err: self.failed.emit(err))

        self._worker: TTSStreamWorker | None = None
        self._job = 0
        self._priority = 0
        self._pitch = 0.0
        self._last_text = ""
        self._speaking = False

    # ------------------------------------------------------------------
    # 설정
    # ------------------------------------------------------------------

    def set_pitch(self, semitones: float) -> None:
        """알림 낭독 톤. 기본 톤 + 알림 부스트를 합친 값을 넣는다."""
        self._pitch = float(semitones or 0.0)
        self._player.set_voice_pitch(self._pitch)

    @property
    def pitch(self) -> float:
        return self._pitch

    @property
    def last_text(self) -> str:
        """REPEAT_ALERT('다시 말해줘') 용 — 마지막으로 읽은 문장."""
        return self._last_text

    def is_speaking(self) -> bool:
        return self._speaking

    # ------------------------------------------------------------------
    # 낭독
    # ------------------------------------------------------------------

    def speak(self, text: str, *, priority: int = AlertPriority.NOTICE) -> bool:
        """즉시 낭독. 이미 말하는 중이면 우선순위를 비교해 결정한다."""
        body = (text or "").strip()
        if not body:
            return False
        if len(body) > MAX_ALERT_CHARS:
            body = body[: MAX_ALERT_CHARS - 1].rstrip() + "…"

        if self._speaking and priority < self._priority:
            return False  # 전화 낭독 중에 일반 알림이 끼어들지 못하게

        self.stop()
        self._priority = priority
        self._last_text = body
        self._job += 1
        job = self._job

        payload = dict(self._payload() or {})
        worker = TTSStreamWorker(
            runtime_url=self._runtime_url(),
            text=body,
            payload=payload,
            parent=self,
        )
        self._worker = worker
        worker.started_fmt.connect(lambda rate, j=job: self._on_format(rate, j))
        worker.chunk.connect(lambda pcm, j=job: self._on_chunk(pcm, j))
        worker.finished_ok.connect(lambda j=job: self._on_stream_done(j))
        worker.failed.connect(lambda err, j=job: self._on_failed(err, j))
        worker.finished.connect(worker.deleteLater)

        self._speaking = True
        self.started.emit(body)
        worker.start()
        return True

    def repeat(self) -> bool:
        """마지막 알림을 다시 읽는다."""
        if not self._last_text:
            return False
        return self.speak(self._last_text, priority=self._priority or AlertPriority.NOTICE)

    def stop(self) -> None:
        self._job += 1  # 진행 중 시그널을 무효화
        worker = self._worker
        self._worker = None
        if worker is not None:
            try:
                worker.request_cancel()
            except Exception:
                pass
        try:
            self._player.stop()
        except Exception:
            pass
        self._speaking = False
        self._priority = 0

    # ------------------------------------------------------------------
    # 스트림 콜백
    # ------------------------------------------------------------------

    def _on_format(self, sample_rate: int, job: int) -> None:
        if job != self._job:
            return
        self._player.set_format(sample_rate)
        # set_format 이 재생기를 리셋할 수 있으므로 피치를 다시 건다
        self._player.set_voice_pitch(self._pitch)

    def _on_chunk(self, pcm: bytes, job: int) -> None:
        if job != self._job:
            return
        self._player.set_volume(self._volume())
        self._player.feed(pcm)

    def _on_stream_done(self, job: int) -> None:
        if job != self._job:
            return
        self._worker = None
        self._player.end_session()

    def _on_failed(self, error: str, job: int) -> None:
        if job != self._job:
            return
        self._worker = None
        self._speaking = False
        self._priority = 0
        self.failed.emit(error or "알림 낭독에 실패했습니다.")

    def _on_drained(self) -> None:
        if not self._speaking:
            return
        self._speaking = False
        self._priority = 0
        self.finished.emit()


# ----------------------------------------------------------------------
# 낭독 문안
# ----------------------------------------------------------------------


def call_announcement(display_name: str, *, number: str = "") -> str:
    """수신 전화 안내 문장.

    번호를 통째로 읽으면 길고 알아듣기 어렵다. 이름을 알면 이름만,
    모르면 뒷자리만 읽어 준다.
    """
    name = (display_name or "").strip()
    tail = (number or "").strip()
    if name and name != tail:
        return f"{name} 님에게 전화가 왔습니다. 받아 드릴까요?"
    if tail:
        digits = "".join(ch for ch in tail if ch.isdigit())
        if len(digits) >= 4:
            return f"뒷자리 {digits[-4:]} 번호로 전화가 왔습니다. 받아 드릴까요?"
    return "전화가 왔습니다. 받아 드릴까요?"


def notification_announcement(title: str, message: str = "") -> str:
    """알림 낭독 문장 — 제목 위주로 짧게."""
    head = (title or "").strip()
    body = (message or "").strip()
    if head and body and body != head:
        return f"{head}. {body}"
    return head or body or "새 알림이 있습니다."
