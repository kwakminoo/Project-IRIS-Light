"""스트리밍 피치 시프터 — 길이를 유지한 채 음높이만 올린다.

아이리스 보이스 프로필(음색)은 그대로 두고 **재생 단계 PCM에서만** 톤을 올린다.
합성 모델의 reference/prompt를 건드리지 않으므로 프로필을 다시 빌드할 필요가 없다.

알고리즘: 크로스페이드 2탭 딜레이라인(그래뉼러 피치 시프트).
  - 쓰기 포인터는 1샘플/샘플, 읽기 포인터는 ratio 샘플/샘플로 전진한다.
  - 읽기가 더 빠르면(ratio > 1) 같은 시간에 더 많은 파형을 훑어 **음이 올라간다**.
  - 읽기 포인터가 딜레이 창을 벗어나면 튀므로, 창의 절반만큼 떨어진 두 탭을
    해닝 크로스페이드로 섞어 이음매를 감춘다.

위상 보코더 대신 이걸 쓰는 이유는 **지연** 때문이다. 위상 보코더는 FFT 프레임
하나(보통 40~60 ms)를 모아야 첫 소리가 나오는데, 이 기능은 알림·전화 낭독용이라
첫 음성 지연이 곧 체감 품질이다. 이 방식은 프레임을 모으지 않고 들어온 만큼
바로 뱉는다(추가 지연 0). 대신 큰 시프트에서 금속성이 생기므로 ±6 반음으로 제한한다.
"""

from __future__ import annotations

from iris.audio.pcm_stream import DEFAULT_SAMPLE_RATE

try:  # numpy 는 requirements.txt 의 핵심 의존성이지만 없어도 죽지 않게 한다
    import numpy as _np
except Exception:  # pragma: no cover - numpy 없는 환경
    _np = None  # type: ignore[assignment]

# 사람 목소리에서 자연스러움이 유지되는 범위. 넘어가면 헬륨 소리가 난다.
MAX_SEMITONES = 6.0
# 딜레이 창. 짧으면 저음이 뭉개지고, 길면 이중창처럼 울린다.
_WINDOW_MS = 42.0


def semitones_to_ratio(semitones: float) -> float:
    """반음 → 주파수 배율. +12 반음이 정확히 2배."""
    value = max(-MAX_SEMITONES, min(MAX_SEMITONES, float(semitones or 0.0)))
    return 2.0 ** (value / 12.0)


class PitchShifter:
    """Int16 mono PCM 스트림의 음높이를 올린다. 길이는 그대로 유지된다.

    청크 경계를 넘어 상태(딜레이라인·읽기 위상)를 유지하므로 스트리밍 중간에
    끊기지 않는다. 문장이 바뀌면 reset() 으로 잔향을 지운다.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, semitones: float = 0.0) -> None:
        self._sample_rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
        self._semitones = 0.0
        self._ratio = 1.0
        self._window = 1
        self._buffer = None  # numpy float32 링버퍼
        self._write = 0
        self._delay = 0.0
        self._rebuild()
        self.set_semitones(semitones)

    # ------------------------------------------------------------------
    # 설정
    # ------------------------------------------------------------------

    @property
    def semitones(self) -> float:
        return self._semitones

    @property
    def active(self) -> bool:
        """실제로 변형이 일어나는 상태인지 — 아니면 process() 가 그대로 통과시킨다."""
        return _np is not None and abs(self._semitones) > 1e-3

    def set_semitones(self, semitones: float) -> None:
        value = max(-MAX_SEMITONES, min(MAX_SEMITONES, float(semitones or 0.0)))
        if abs(value - self._semitones) < 1e-6:
            return
        self._semitones = value
        self._ratio = semitones_to_ratio(value)
        self.reset()

    def set_sample_rate(self, sample_rate: int) -> None:
        rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
        if rate == self._sample_rate:
            return
        self._sample_rate = rate
        self._rebuild()

    def reset(self) -> None:
        """문장 경계 — 이전 문장 꼬리가 다음 문장에 섞이지 않도록 비운다."""
        if self._buffer is not None:
            self._buffer[:] = 0.0
        self._write = 0
        self._delay = 0.0

    # ------------------------------------------------------------------
    # 처리
    # ------------------------------------------------------------------

    def process(self, pcm: bytes) -> bytes:
        """들어온 길이 그대로 돌려준다. 홀수 바이트 꼬리는 손대지 않고 붙인다."""
        if not pcm or not self.active:
            return pcm

        aligned = len(pcm) & ~1
        if not aligned:
            return pcm
        tail = pcm[aligned:]

        samples = _np.frombuffer(pcm[:aligned], dtype="<i2").astype(_np.float32)
        if samples.shape[0] == 0:
            return pcm

        # 한 번에 쓰는 양이 링버퍼 절반을 넘으면, 아직 읽어야 할 과거 구간을
        # 덮어써 버린다. 청크 크기는 호출 측 사정이므로 여기서 잘라 처리한다.
        limit = max(1, self._window // 2)
        if samples.shape[0] <= limit:
            out = self._process_block(samples)
        else:
            pieces = [
                self._process_block(samples[i : i + limit])
                for i in range(0, samples.shape[0], limit)
            ]
            out = _np.concatenate(pieces)
        return out.tobytes() + tail

    def _process_block(self, samples):
        """링버퍼 절반 이하 길이의 블록 하나를 변환한다."""
        count = samples.shape[0]
        window = self._window
        buffer = self._buffer
        write = self._write
        offsets = _np.arange(count, dtype=_np.float64)

        # 1) 링버퍼에 기록 — 청크가 창보다 길어도 되도록 모듈로 인덱스로 흩뿌린다
        write_idx = (write + _np.arange(count, dtype=_np.int64)) % window
        buffer[write_idx] = samples

        # 2) 읽기 지연(delay)이 (ratio - 1) 만큼씩 줄어든다.
        #    지연이 줄면 = 읽기가 쓰기를 따라잡으면 = 파형을 빨리 훑으면 음이 올라간다.
        #    창을 벗어나면 모듈로로 되감고, 그 이음매는 아래 크로스페이드가 가린다.
        drift = self._ratio - 1.0
        delay = _np.mod(self._delay - drift * offsets, float(window))

        # 3) 두 탭 — 창의 절반만큼 지연을 벌려 이음매가 겹치지 않게 한다
        read_a = _np.mod(write + offsets - delay, float(window))
        read_b = _np.mod(read_a - window * 0.5, float(window))

        first = self._interp(buffer, read_a, window)
        second = self._interp(buffer, read_b, window)

        # 4) 해닝 크로스페이드.
        #    delay 가 0/창끝에 가까우면 탭 A 가 쓰기 포인터 위에 올라타 튄다.
        #    그 구간에서는 반대편(탭 B)에 가중치를 준다.
        fade = 0.5 - 0.5 * _np.cos(2.0 * _np.pi * delay / window)
        mixed = first * fade + second * (1.0 - fade)

        self._write = int((write + count) % window)
        self._delay = float(_np.mod(self._delay - drift * count, float(window)))

        return _np.clip(_np.rint(mixed), -32768.0, 32767.0).astype("<i2")

    # ------------------------------------------------------------------

    @staticmethod
    def _interp(buffer, positions, window: int):
        """링버퍼 선형 보간 — 정수 인덱싱만 쓰면 지글거린다."""
        low = positions.astype(_np.int64) % window
        high = (low + 1) % window
        frac = (positions - _np.floor(positions)).astype(_np.float32)
        return buffer[low] * (1.0 - frac) + buffer[high] * frac

    def _rebuild(self) -> None:
        size = max(64, int(self._sample_rate * _WINDOW_MS / 1000.0))
        self._window = size
        if _np is None:
            self._buffer = None
            return
        self._buffer = _np.zeros(size, dtype=_np.float32)
        self._write = 0
        self._delay = 0.0


def shift_pcm(pcm: bytes, semitones: float, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """일회성 변환 — 테스트/짧은 알림용. 스트리밍에는 PitchShifter 를 쓴다."""
    if not pcm or abs(float(semitones or 0.0)) < 1e-3:
        return pcm
    return PitchShifter(sample_rate, semitones).process(pcm)
