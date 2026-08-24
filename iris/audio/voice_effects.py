"""절제된 AI 비서 질감용, 상태를 유지하는 PCM 후처리."""

from __future__ import annotations

from array import array
import sys

from iris.audio.pcm_stream import DEFAULT_SAMPLE_RATE
from iris.audio.pitch_shift import PitchShifter


class VoiceAssistantEffect:
    """Int16 mono PCM의 톤을 올리고 짧은 echo와 아주 약한 metallic comb을 더한다.

    합성 모델의 reference/prompt는 건드리지 않고, 스트리밍 PCM 뒤에서만 작동한다.
    피치는 echo보다 **먼저** 적용한다 — 반대로 하면 잔향까지 같이 올라가
    금속성이 두 배로 들린다.
    """

    _ECHO_MS = 82
    _METALLIC_MS = 7

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self._enabled = False
        self._intensity = 0.75
        self._sample_rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
        self._echo_delay: array[int] = array("h")
        self._metallic_delay: array[int] = array("h")
        self._echo_index = 0
        self._metallic_index = 0
        self._pitch = PitchShifter(self._sample_rate, 0.0)
        self._rebuild_delays()

    def set_pitch(self, semitones: float) -> None:
        """보이스 프로필은 그대로 두고 재생 톤만 올린다(반음 단위)."""
        self._pitch.set_semitones(semitones)

    @property
    def pitch_semitones(self) -> float:
        return self._pitch.semitones

    def configure(self, *, enabled: bool, intensity: float) -> None:
        value = max(0.0, min(1.0, float(intensity)))
        changed = self._enabled != bool(enabled) or self._intensity != value
        self._enabled = bool(enabled)
        self._intensity = value
        if changed:
            self.reset()

    def set_sample_rate(self, sample_rate: int) -> None:
        rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
        if rate == self._sample_rate:
            return
        self._sample_rate = rate
        self._pitch.set_sample_rate(rate)
        self._rebuild_delays()
        self.reset()

    def reset(self) -> None:
        self._pitch.reset()
        self._echo_index = 0
        self._metallic_index = 0
        if self._echo_delay:
            self._echo_delay[:] = array("h", [0]) * len(self._echo_delay)
        if self._metallic_delay:
            self._metallic_delay[:] = array("h", [0]) * len(self._metallic_delay)

    def process(self, pcm: bytes) -> bytes:
        """원본 길이/형식을 유지하면서 현재 PCM 조각을 처리한다."""
        if not pcm:
            return pcm

        # 피치는 AI 음향 효과와 독립이다. 효과를 꺼도 톤은 올라가야 한다.
        pcm = self._pitch.process(pcm)

        if not self._enabled or self._intensity <= 0.0:
            return pcm

        aligned = len(pcm) & ~1
        if not aligned:
            return pcm
        samples = array("h")
        samples.frombytes(pcm[:aligned])
        if sys.byteorder != "little":
            samples.byteswap()

        # Intensity 0에는 완전한 dry, 1에는 여전히 알아들을 수 있는 upper bound를 둔다.
        echo_mix = 0.22 * self._intensity
        metallic_mix = 0.08 * self._intensity
        dry_mix = 1.0 - echo_mix - metallic_mix
        echo_delay = self._echo_delay
        metallic_delay = self._metallic_delay
        echo_index = self._echo_index
        metallic_index = self._metallic_index

        for index, sample in enumerate(samples):
            echo = echo_delay[echo_index]
            metallic = metallic_delay[metallic_index]
            mixed = int(round(sample * dry_mix + echo * echo_mix + metallic * metallic_mix))
            samples[index] = max(-32768, min(32767, mixed))
            echo_delay[echo_index] = sample
            metallic_delay[metallic_index] = sample
            echo_index = (echo_index + 1) % len(echo_delay)
            metallic_index = (metallic_index + 1) % len(metallic_delay)

        self._echo_index = echo_index
        self._metallic_index = metallic_index
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes() + pcm[aligned:]

    def _rebuild_delays(self) -> None:
        echo_samples = max(1, round(self._sample_rate * self._ECHO_MS / 1000.0))
        metallic_samples = max(1, round(self._sample_rate * self._METALLIC_MS / 1000.0))
        self._echo_delay = array("h", [0]) * echo_samples
        self._metallic_delay = array("h", [0]) * metallic_samples
        self._echo_index = 0
        self._metallic_index = 0
