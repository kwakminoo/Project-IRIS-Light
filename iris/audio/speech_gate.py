"""RMS 임계치 기반 발화 구간 검출 (연속 청취용)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpeechGate:
    """ponytail: 단순 프레임 카운트 VAD — 천장=노이즈/말겹침, 업그레이드=Silero VAD."""

    speech_rms: float = 0.02
    start_frames: int = 3  # ~150ms @50ms poll
    end_frames: int = 10  # ~500ms silence
    speaking: bool = False
    _above: int = 0
    _below: int = 0

    def set_speech_rms(self, rms: float) -> None:
        self.speech_rms = max(0.001, float(rms))

    def reset(self) -> None:
        self.speaking = False
        self._above = 0
        self._below = 0

    def feed(self, rms: float) -> str:
        """'' | 'start' | 'end'."""
        if rms >= self.speech_rms:
            self._above += 1
            self._below = 0
            if not self.speaking and self._above >= self.start_frames:
                self.speaking = True
                return "start"
            return ""
        self._below += 1
        self._above = 0
        if self.speaking and self._below >= self.end_frames:
            self.speaking = False
            return "end"
        return ""
