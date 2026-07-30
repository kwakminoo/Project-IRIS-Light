"""첫 기동 UI 등장 연출 — 무료 모델 확인 중 로딩바 없이 '준비 중' 느낌."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPauseAnimation,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

if TYPE_CHECKING:
    from iris.ui.widgets.mic_waveform_bar import MicWaveformBar
    from iris.ui.widgets.particle_visualizer import ParticleVisualizer


class _SlideFadeProxy(QObject):
    """레이아웃 위젯용 페이드 + Y 오프셋(살짝 위에서 내려옴)."""

    def __init__(self, widget: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._widget = widget
        self._base_y = 0
        self._offset = 0.0
        self._opacity = 1.0
        self._effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1.0)
        self._armed = False

    def arm(self, start_offset: float = -28.0) -> None:
        self._base_y = self._widget.y()
        self._armed = True
        self.setOffset(start_offset)
        self.setOpacity(0.0)

    def getOffset(self) -> float:  # noqa: N802
        return self._offset

    def setOffset(self, value: float) -> None:  # noqa: N802
        self._offset = float(value)
        if self._armed:
            self._widget.move(self._widget.x(), int(self._base_y + self._offset))

    offset = pyqtProperty(float, getOffset, setOffset)

    def getOpacity(self) -> float:  # noqa: N802
        return self._opacity

    def setOpacity(self, value: float) -> None:  # noqa: N802
        self._opacity = max(0.0, min(1.0, float(value)))
        self._effect.setOpacity(self._opacity)

    opacity = pyqtProperty(float, getOpacity, setOpacity)

    def finish(self) -> None:
        self._armed = False
        self.setOffset(0.0)
        self.setOpacity(1.0)
        self._widget.setGraphicsEffect(None)
        self._effect = None  # type: ignore[assignment]


class _SideSlideProxy(QObject):
    """좌·우 세로 패널 — 폭 + 투명도로 슬라이드 인."""

    def __init__(
        self,
        widget: QWidget,
        *,
        from_left: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._widget = widget
        self._from_left = from_left
        self._min_w = widget.minimumWidth()
        self._max_w = widget.maximumWidth()
        self._progress = 1.0
        self._opacity = 1.0
        self._effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(self._effect)
        self._target_w = max(widget.width(), self._min_w, 1)

    def arm(self) -> None:
        self._target_w = max(self._widget.width(), self._min_w, 1)
        self.setProgress(0.0)
        self.setOpacity(0.0)

    def getProgress(self) -> float:  # noqa: N802
        return self._progress

    def setProgress(self, value: float) -> None:  # noqa: N802
        self._progress = max(0.0, min(1.0, float(value)))
        w = max(0, int(self._target_w * self._progress))
        self._widget.setMinimumWidth(w if self._progress > 0.02 else 0)
        self._widget.setMaximumWidth(w if self._progress < 0.98 else self._max_w)
        if self._from_left:
            # 레이아웃이 좌측 고정이므로 폭만으로도 슬라이드 감이 난다.
            pass

    progress = pyqtProperty(float, getProgress, setProgress)

    def getOpacity(self) -> float:  # noqa: N802
        return self._opacity

    def setOpacity(self, value: float) -> None:  # noqa: N802
        self._opacity = max(0.0, min(1.0, float(value)))
        self._effect.setOpacity(self._opacity)

    opacity = pyqtProperty(float, getOpacity, setOpacity)

    def finish(self) -> None:
        self._widget.setMinimumWidth(self._min_w)
        self._widget.setMaximumWidth(self._max_w)
        self.setOpacity(1.0)
        self._widget.setGraphicsEffect(None)
        self._effect = None  # type: ignore[assignment]


class _OrbBootProxy(QObject):
    """구체 — 디지털 치지직 reveal."""

    def __init__(self, orb: ParticleVisualizer, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._orb = orb
        self._reveal = 0.0
        self._glitch = 0.0

    def arm(self) -> None:
        self.setReveal(0.0)
        self.setGlitch(1.0)

    def getReveal(self) -> float:  # noqa: N802
        return self._reveal

    def setReveal(self, value: float) -> None:  # noqa: N802
        self._reveal = max(0.0, min(1.0, float(value)))
        self._orb.set_boot_reveal(self._reveal)

    reveal = pyqtProperty(float, getReveal, setReveal)

    def getGlitch(self) -> float:  # noqa: N802
        return self._glitch

    def setGlitch(self, value: float) -> None:  # noqa: N802
        self._glitch = max(0.0, min(1.0, float(value)))
        self._orb.set_boot_glitch(self._glitch)

    glitch = pyqtProperty(float, getGlitch, setGlitch)

    def finish(self) -> None:
        self._orb.set_boot_reveal(1.0)
        self._orb.set_boot_glitch(0.0)


class _WaveRevealProxy(QObject):
    """음성 파형 — 가운데서 좌우로 뻗어남."""

    def __init__(self, wave: MicWaveformBar, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._wave = wave
        self._progress = 0.0

    def arm(self) -> None:
        self.setProgress(0.0)

    def getProgress(self) -> float:  # noqa: N802
        return self._progress

    def setProgress(self, value: float) -> None:  # noqa: N802
        self._progress = max(0.0, min(1.0, float(value)))
        self._wave.set_reveal_progress(self._progress)

    progress = pyqtProperty(float, getProgress, setProgress)

    def finish(self) -> None:
        self._wave.set_reveal_progress(1.0)


class StartupIntroAnimator(QObject):
    """
    빈 창 → 좌우 세로바 슬라이드 → 구체 치지직 → 로그/채팅 페이드·슬라이드
    → 파형 좌우 확장. 모델 로드가 끝나기 전엔 연출이 '준비 중' 역할을 한다.
    """

    finished = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._left: _SideSlideProxy | None = None
        self._right: _SideSlideProxy | None = None
        self._orb: _OrbBootProxy | None = None
        self._live: _SlideFadeProxy | None = None
        self._chat: _SlideFadeProxy | None = None
        self._wave: _WaveRevealProxy | None = None
        self._chrome: list[_SlideFadeProxy] = []
        self._group: QSequentialAnimationGroup | None = None
        self._models_ready = False
        self._motion_done = False
        self._started = False
        self._completed = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._try_complete)

    def bind(
        self,
        *,
        left: QWidget,
        right: QWidget,
        orb: ParticleVisualizer,
        live: QWidget,
        chat: QWidget,
        waveform: MicWaveformBar,
        chrome: list[QWidget] | None = None,
    ) -> None:
        self._left = _SideSlideProxy(left, from_left=True, parent=self)
        self._right = _SideSlideProxy(right, from_left=False, parent=self)
        self._orb = _OrbBootProxy(orb, parent=self)
        self._live = _SlideFadeProxy(live, parent=self)
        self._chat = _SlideFadeProxy(chat, parent=self)
        self._wave = _WaveRevealProxy(waveform, parent=self)
        self._chrome = [_SlideFadeProxy(w, parent=self) for w in (chrome or [])]

    def prepare_hidden(self) -> None:
        """첫 레이아웃 직후 — 빈 창처럼 보이도록 숨김 상태."""
        if self._left:
            self._left.arm()
        if self._right:
            self._right.arm()
        if self._orb:
            self._orb.arm()
        if self._live:
            self._live.arm(-32.0)
        if self._chat:
            self._chat.arm(-36.0)
        if self._wave:
            self._wave.arm()
        for c in self._chrome:
            c.arm(-12.0)

    def start(self) -> None:
        if self._started or self._left is None:
            return
        self._started = True
        # 레이아웃이 최종 좌표를 잡은 뒤 기준점 재측정
        QTimer.singleShot(0, self._arm_and_run)

    def notify_models_ready(self) -> None:
        self._models_ready = True
        self._try_complete()

    def _arm_and_run(self) -> None:
        assert self._left and self._right and self._orb
        assert self._live and self._chat and self._wave

        # 폭 타깃·Y 기준을 현재 geometry로 다시 잡음
        self._left.arm()
        self._right.arm()
        self._orb.arm()
        self._live.arm(-32.0)
        self._chat.arm(-36.0)
        self._wave.arm()
        for c in self._chrome:
            c.arm(-12.0)

        seq = QSequentialAnimationGroup(self)
        self._group = seq

        # 1) 크롬(상단) 살짝 + 좌우 세로바 슬라이드
        phase1 = QParallelAnimationGroup()
        phase1.addAnimation(self._side_anim(self._left, 720))
        phase1.addAnimation(self._side_anim(self._right, 720))
        for c in self._chrome:
            phase1.addAnimation(self._fade_slide_anim(c, 520, delay=80))
        seq.addAnimation(phase1)

        # 2) 구체 치지직 등장 (reveal↑, glitch↓)
        phase2 = QParallelAnimationGroup()
        reveal = QPropertyAnimation(self._orb, b"reveal")
        reveal.setDuration(900)
        reveal.setStartValue(0.0)
        reveal.setEndValue(1.0)
        reveal.setEasingCurve(QEasingCurve.Type.OutCubic)
        glitch = QPropertyAnimation(self._orb, b"glitch")
        glitch.setDuration(1100)
        glitch.setStartValue(1.0)
        glitch.setEndValue(0.0)
        glitch.setEasingCurve(QEasingCurve.Type.InOutQuad)
        phase2.addAnimation(reveal)
        phase2.addAnimation(glitch)
        seq.addAnimation(phase2)

        # 3) 로그창·채팅창·입력창 위에서 페이드 인
        phase3 = QParallelAnimationGroup()
        phase3.addAnimation(self._fade_slide_anim(self._live, 640, delay=0))
        phase3.addAnimation(self._fade_slide_anim(self._chat, 720, delay=90))
        seq.addAnimation(phase3)

        # 4) 마지막으로 음성 파형 좌우 확장
        wave = QPropertyAnimation(self._wave, b"progress")
        wave.setDuration(780)
        wave.setStartValue(0.0)
        wave.setEndValue(1.0)
        wave.setEasingCurve(QEasingCurve.Type.OutCubic)
        seq.addAnimation(wave)

        seq.finished.connect(self._on_motion_finished)
        seq.start()

    def _side_anim(self, proxy: _SideSlideProxy, duration: int) -> QParallelAnimationGroup:
        group = QParallelAnimationGroup()
        prog = QPropertyAnimation(proxy, b"progress")
        prog.setDuration(duration)
        prog.setStartValue(0.0)
        prog.setEndValue(1.0)
        prog.setEasingCurve(QEasingCurve.Type.OutCubic)
        opac = QPropertyAnimation(proxy, b"opacity")
        opac.setDuration(int(duration * 0.75))
        opac.setStartValue(0.0)
        opac.setEndValue(1.0)
        opac.setEasingCurve(QEasingCurve.Type.OutQuad)
        group.addAnimation(prog)
        group.addAnimation(opac)
        return group

    def _fade_slide_anim(
        self,
        proxy: _SlideFadeProxy,
        duration: int,
        *,
        delay: int = 0,
    ) -> QSequentialAnimationGroup | QParallelAnimationGroup:
        group = QParallelAnimationGroup()
        off = QPropertyAnimation(proxy, b"offset")
        off.setDuration(duration)
        off.setStartValue(proxy.getOffset())
        off.setEndValue(0.0)
        off.setEasingCurve(QEasingCurve.Type.OutCubic)
        opac = QPropertyAnimation(proxy, b"opacity")
        opac.setDuration(duration)
        opac.setStartValue(0.0)
        opac.setEndValue(1.0)
        opac.setEasingCurve(QEasingCurve.Type.OutQuad)
        group.addAnimation(off)
        group.addAnimation(opac)
        if delay <= 0:
            return group
        return self._with_delay_group(group, delay)

    def _with_delay_group(
        self,
        anim: QParallelAnimationGroup,
        delay_ms: int,
    ) -> QSequentialAnimationGroup:
        wrapped = QSequentialAnimationGroup()
        wrapped.addAnimation(QPauseAnimation(delay_ms))
        wrapped.addAnimation(anim)
        return wrapped

    def _on_motion_finished(self) -> None:
        self._motion_done = True
        # 모델 프로브가 아직이면 짧게 대기(연출이 로딩 역할)
        if not self._models_ready:
            self._hold_timer.start(120)
            return
        self._try_complete()

    def _try_complete(self) -> None:
        if self._completed:
            return
        if not self._motion_done:
            return
        if not self._models_ready:
            # 모델 확인이 길면 구체에 약한 글리치만 유지
            if self._orb is not None:
                self._orb.setGlitch(0.18)
            self._hold_timer.start(180)
            return
        self._completed = True
        self._hold_timer.stop()
        if self._orb is not None:
            self._orb.finish()
        if self._left is not None:
            self._left.finish()
        if self._right is not None:
            self._right.finish()
        if self._live is not None:
            self._live.finish()
        if self._chat is not None:
            self._chat.finish()
        if self._wave is not None:
            self._wave.finish()
        for c in self._chrome:
            c.finish()
        self.finished.emit()
