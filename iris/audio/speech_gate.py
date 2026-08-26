"""RMS pre-gate + Silero VAD 발화 구간 검출."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpeechGate:
    """RMS로 잔소음을 버리고, Silero(또는 RMS fallback)로 발화를 확정한다."""

    speech_rms: float = 0.02
    start_frames: int = 3  # ~150ms @50ms poll
    end_frames: int = 8  # ~400ms silence
    min_speech_frames: int = 2  # recorder는 4로 올려 click 폐기
    max_speech_frames: int = 240  # ~12s
    vad_speech_prob: float = 0.5
    speaking: bool = False
    noise_floor: float = 0.008
    _above: int = 0
    _below: int = 0
    _speech_frames: int = 0
    _noise_rms: list[float] = field(default_factory=list)
    _calibrating: bool = True
    _cal_frames_left: int = 30  # ~1.5s
    _had_speech_during_cal: bool = False

    def set_speech_rms(self, rms: float) -> None:
        self.speech_rms = max(0.001, float(rms))

    def reset(self) -> None:
        self.clear_speech()
        self._noise_rms = []
        self._calibrating = True
        self._cal_frames_left = 30
        self._had_speech_during_cal = False
        self.noise_floor = 0.008

    def clear_speech(self) -> None:
        self.speaking = False
        self._above = 0
        self._below = 0
        self._speech_frames = 0

    def adaptive_threshold(self) -> float:
        # 덜 민감(높은 speech_rms) → 더 높은 문턱
        sensitivity = max(0.001, self.speech_rms) / 0.02
        # noise_floor가 튀는 구간(초기 스피치 포함)에서도 speech_rms 이상으로 문턱이 커지지 않게 캡
        raw = self.noise_floor * 1.6 * sensitivity
        speech_rms = max(0.001, float(self.speech_rms))
        threshold = min(speech_rms, raw)
        return max(0.001, threshold)

    def feed(self, rms: float, vad_prob: float | None = None) -> str:
        """'' | 'start' | 'end' | 'drop'."""
        rms = float(rms)
        threshold = self.adaptive_threshold()
        # RMS pre-gate: 아주 작은 소음은 VAD도 안 태운 것과 동일하게 침묵
        rms_hot = rms >= threshold
        if self.speaking:
            # ponytail: 발화 중엔 RMS로 유지만 — Silero가 끊기면 utterance_ready가 영원히 안 뜬다
            is_speech = rms_hot
        elif vad_prob is None:
            is_speech = rms_hot
        else:
            is_speech = rms_hot and float(vad_prob) >= self.vad_speech_prob
            if rms_hot and not is_speech and rms >= threshold * 3.0 and vad_prob < 0.15:
                # 충격/클릭류: RMS는 큰데 음성 확률은 낮음
                is_speech = False

        if self._calibrating and not self.speaking:
            if is_speech:
                self._had_speech_during_cal = True
            else:
                self._noise_rms.append(rms)
            self._cal_frames_left -= 1
            if self._cal_frames_left <= 0:
                self._calibrating = False
                if self._noise_rms:
                    ordered = sorted(self._noise_rms)
                    # ponytail: 초기 구간에 유입된 발화가 noise_floor를 과대평가하는 문제 완화
                    ratio = 0.25 if self._had_speech_during_cal else 0.5
                    idx = int(len(ordered) * ratio)
                    idx = max(0, min(len(ordered) - 1, idx))
                    self.noise_floor = max(0.002, ordered[idx])
            elif not is_speech and len(self._noise_rms) >= 8:
                ordered = sorted(self._noise_rms[-24:])
                self.noise_floor = max(0.002, ordered[len(ordered) // 2])
        elif not self.speaking and not is_speech:
            self._noise_rms.append(rms)
            if len(self._noise_rms) > 80:
                self._noise_rms = self._noise_rms[-80:]
            ordered = sorted(self._noise_rms)
            self.noise_floor = max(0.002, ordered[len(ordered) // 2])

        if is_speech:
            self._above += 1
            self._below = 0
            if not self.speaking and self._above >= self.start_frames:
                self.speaking = True
                self._speech_frames = self._above
                return "start"
            if self.speaking:
                self._speech_frames += 1
                if self._speech_frames >= self.max_speech_frames:
                    self.speaking = False
                    self._above = 0
                    self._below = 0
                    frames = self._speech_frames
                    self._speech_frames = 0
                    return "end" if frames >= self.min_speech_frames else "drop"
            return ""
        self._below += 1
        self._above = 0
        if self.speaking and self._below >= self.end_frames:
            self.speaking = False
            frames = self._speech_frames
            self._speech_frames = 0
            self._below = 0
            return "end" if frames >= self.min_speech_frames else "drop"
        return ""
