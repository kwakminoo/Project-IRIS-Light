"""실시간 TTS용 semantic chunker + GPU를 쉬지 않고 돌리는 합성 결정."""

from __future__ import annotations

import re
import time

from iris.audio.text_normalizer import DEFAULT_PRONUNCIATIONS, normalize_tts_text


# 대화 스트림은 첫 절을 짧게 내보내고, 이후에는 문장 사이 gap을 줄일 만큼 묶는다.
TTS_STREAM_MIN_CHARS = 18
TTS_STREAM_FIRST_TARGET_CHARS = 48
TTS_STREAM_FIRST_MAX_CHARS = 72
TTS_STREAM_LATER_TARGET_CHARS = 140
TTS_STREAM_LATER_MAX_CHARS = 180
TTS_STREAM_SOFT_FLUSH_MS = 320

_SENT_END = frozenset(".!?。！？")
_CLAUSE_END = frozenset(",，;；:")
_URL_OR_PATH = re.compile(
    r"https?://\S+|www\.\S+|\b[A-Za-z]:\\\S+|\b/(?:Users|home|var|tmp|opt)/\S+"
)
_PARTIAL_URL_OR_PATH = re.compile(
    r"(?:https?(?::/{0,2})?|www\.?|[A-Za-z]:\\?|/(?:Users|home|var|tmp|opt)(?:/\S*)?)$",
    re.IGNORECASE,
)


def should_start_tts_synth(
    *,
    synthesizing: bool,
    pending_count: int,
    ready_count: int = 0,
    prefetch_depth: int | None = None,
) -> bool:
    """pending이 남아 있으면 GPU를 쉬게 두지 않는다. ready 개수는 무시."""
    del ready_count, prefetch_depth
    return (not synthesizing) and pending_count > 0


def _fenced_ranges(text: str) -> tuple[list[tuple[int, int]], int]:
    """완결된 fenced-code 범위와 안전하게 읽을 수 있는 끝 위치를 구한다."""
    ranges: list[tuple[int, int]] = []
    start = 0
    while True:
        opening = text.find("```", start)
        if opening < 0:
            return ranges, len(text)
        closing = text.find("```", opening + 3)
        if closing < 0:
            # 닫히지 않은 code block 안은 다음 LLM 청크까지 말하지 않는다.
            return ranges, opening
        end = closing + 3
        ranges.append((opening, end))
        start = end


def _split_positions(
    text: str,
    visible_end: int,
    *,
    allow_trailing_token: bool,
) -> dict[str, list[int]]:
    """단어/보호 토큰을 가르지 않는 후보 split 위치를 분류한다."""
    code_ranges, _ = _fenced_ranges(text)
    protected = list(code_ranges)
    trailing_token_start: int | None = None
    for match in _URL_OR_PATH.finditer(text[:visible_end]):
        start, end = match.span()
        protected.append((start, end))
        if end == visible_end:
            trailing_token_start = start
    partial = _PARTIAL_URL_OR_PATH.search(text[:visible_end])
    if partial is not None and (
        trailing_token_start is None or partial.start() < trailing_token_start
    ):
        trailing_token_start = partial.start()

    positions = {"sentence": [], "clause": [], "space": []}
    for index, char in enumerate(text[:visible_end]):
        end = index + 1
        if any(start < end < finish for start, finish in protected):
            continue
        if (
            not allow_trailing_token
            and trailing_token_start is not None
            and end > trailing_token_start
        ):
            continue
        is_decimal_point = (
            char == "."
            and index > 0
            and end < visible_end
            and text[index - 1].isdigit()
            and text[end].isdigit()
        )
        if char in _SENT_END and not is_decimal_point:
            positions["sentence"].append(end)
        elif char in _CLAUSE_END or char in "\r\n":
            positions["clause"].append(end)
        elif char in " \t":
            positions["space"].append(end)
    return positions


def _trimmed_length(text: str, end: int) -> int:
    return len(text[:end].strip())


def _semantic_cut(
    text: str,
    visible_end: int,
    *,
    cap: int,
    min_chars: int,
    allow_trailing_token: bool,
) -> int | None:
    """우선순위(문장 > 절 > 어절) 안에서 cap 전 가장 자연스러운 끝을 찾는다."""
    positions = _split_positions(
        text, visible_end, allow_trailing_token=allow_trailing_token
    )
    for kind in ("sentence", "clause", "space"):
        candidates = [
            pos
            for pos in positions[kind]
            if pos <= cap and _trimmed_length(text, pos) >= min_chars
        ]
        if candidates:
            return candidates[-1]
    return None


def _first_sentence_cut(
    text: str,
    visible_end: int,
    *,
    cap: int,
    min_chars: int,
    allow_trailing_token: bool,
) -> int | None:
    positions = _split_positions(
        text, visible_end, allow_trailing_token=allow_trailing_token
    )
    candidates = [
        pos
        for pos in positions["sentence"]
        if pos <= cap and _trimmed_length(text, pos) >= min_chars
    ]
    return candidates[0] if candidates else None


def _forced_cut(
    text: str,
    visible_end: int,
    cap: int,
    *,
    final: bool,
) -> int | None:
    """공백도 없는 장문만 마지막 수단으로 분리한다."""
    limit = min(max(1, cap), visible_end)
    code_ranges, _ = _fenced_ranges(text)
    protected = list(code_ranges)
    protected.extend(match.span() for match in _URL_OR_PATH.finditer(text[:visible_end]))
    partial = _PARTIAL_URL_OR_PATH.search(text[:visible_end])
    if partial is not None:
        protected.append(partial.span())
    for start, finish in protected:
        if start < limit < finish:
            # 완결 응답에서는 URL/path 전체를 normalizer에 넘겨야 뒤쪽 조각이 말해지지 않는다.
            if final:
                return visible_end
            limit = start
            break
    return limit or None


class TtsSentencePump:
    """LLM 스트림을 자연스러운 TTS 절로 전환한다.

    ``poll()``은 UI timer에서 호출할 수 있다. 입력이 잠시 멈춘 경우에만
    최소 길이를 충족한 절을 soft-flush하므로 토큰마다 짧게 말하지 않는다.
    """

    def __init__(
        self,
        pronunciation_map: dict[str, str] | None = None,
        *,
        min_chars: int = TTS_STREAM_MIN_CHARS,
        first_target_chars: int = TTS_STREAM_FIRST_TARGET_CHARS,
        first_max_chars: int = TTS_STREAM_FIRST_MAX_CHARS,
        later_target_chars: int = TTS_STREAM_LATER_TARGET_CHARS,
        later_max_chars: int = TTS_STREAM_LATER_MAX_CHARS,
        soft_flush_ms: int = TTS_STREAM_SOFT_FLUSH_MS,
    ) -> None:
        self._map = DEFAULT_PRONUNCIATIONS if pronunciation_map is None else pronunciation_map
        self._buf = ""
        self._first_done = False
        self._min = max(1, int(min_chars))
        self._first_max = max(1, int(first_max_chars))
        self._first_target = min(
            self._first_max, max(self._min, int(first_target_chars))
        )
        self._later_max = max(1, int(later_max_chars))
        self._later_target = min(
            self._later_max, max(self._min, int(later_target_chars))
        )
        self._soft_flush_sec = max(0.0, int(soft_flush_ms) / 1000.0)
        self._last_input_at: float | None = None

    def feed(self, chunk: str, *, now: float | None = None) -> list[str]:
        """새 LLM 텍스트를 넣고, 바로 말할 수 있는 절을 반환한다."""
        current = time.monotonic() if now is None else float(now)
        out: list[str] = []
        if chunk and self._is_soft_due(current):
            out.extend(self._drain(soft=True, final=False))
        if chunk:
            self._buf += chunk
            self._last_input_at = current
        out.extend(self._drain(soft=False, final=False))
        return out

    def poll(self, *, now: float | None = None) -> list[str]:
        """soft latency deadline이 지난 경우에만 안전한 절을 하나 이상 내보낸다."""
        current = time.monotonic() if now is None else float(now)
        return self._drain(soft=True, final=False) if self._is_soft_due(current) else []

    def flush(self) -> list[str]:
        """LLM 완료 시 남은 텍스트를 한 번만 내보낸다. 재호출해도 중복하지 않는다."""
        # 완결되지 않은 fenced code는 기존 TTS 정책상 말할 본문이 아니므로 버린다.
        _, visible_end = _fenced_ranges(self._buf)
        if visible_end < len(self._buf):
            self._buf = self._buf[:visible_end]
        out = self._drain(soft=True, final=True)
        self._last_input_at = None
        return out

    def _is_soft_due(self, now: float) -> bool:
        return (
            bool(self._buf)
            and self._last_input_at is not None
            and now - self._last_input_at >= self._soft_flush_sec
        )

    def _drain(self, *, soft: bool, final: bool) -> list[str]:
        out: list[str] = []
        while self._buf:
            code_ranges, visible_end = _fenced_ranges(self._buf)
            if code_ranges:
                lead = len(self._buf) - len(self._buf.lstrip())
                first_start, first_end = code_ranges[0]
                if first_start == lead:
                    # 완결 code block만 단독으로 앞에 있으면 즉시 소비해 버퍼를 묶어두지 않는다.
                    self._consume(first_end, out)
                    continue
            if visible_end <= 0:
                break
            cut = self._next_cut(visible_end, soft=soft, final=final)
            if cut is None:
                break
            self._consume(cut, out)
        return out

    def _next_cut(self, visible_end: int, *, soft: bool, final: bool) -> int | None:
        available = _trimmed_length(self._buf, visible_end)
        if not available:
            return visible_end
        allow_trailing_token = final
        if not self._first_done:
            sentence = _first_sentence_cut(
                self._buf,
                visible_end,
                cap=self._first_max,
                min_chars=1 if final else self._min,
                allow_trailing_token=allow_trailing_token,
            )
            if sentence is not None:
                return sentence
            if available >= self._first_max:
                return _semantic_cut(
                    self._buf,
                    visible_end,
                    cap=self._first_max,
                    min_chars=self._min,
                    allow_trailing_token=allow_trailing_token,
                ) or _forced_cut(
                    self._buf, visible_end, self._first_max, final=final
                )
            if available >= self._first_target:
                cut = _semantic_cut(
                    self._buf,
                    visible_end,
                    cap=visible_end,
                    min_chars=self._min,
                    allow_trailing_token=allow_trailing_token,
                )
                if cut is not None:
                    return cut
            if soft and available >= self._min:
                return _semantic_cut(
                    self._buf,
                    visible_end,
                    cap=visible_end,
                    min_chars=self._min,
                    allow_trailing_token=False,
                )
            if final:
                return visible_end
            return None

        if final and available <= self._later_max:
            return visible_end
        if available >= self._later_max:
            return _semantic_cut(
                self._buf,
                visible_end,
                cap=self._later_max,
                min_chars=self._min,
                allow_trailing_token=allow_trailing_token,
            ) or _forced_cut(
                self._buf, visible_end, self._later_max, final=final
            )
        if available >= self._later_target or (soft and available >= self._min):
            return _semantic_cut(
                self._buf,
                visible_end,
                cap=visible_end,
                min_chars=self._min,
                allow_trailing_token=allow_trailing_token,
            )
        return None

    def _consume(self, cut: int, out: list[str]) -> None:
        raw, self._buf = self._buf[:cut], self._buf[cut:]
        spoken = normalize_tts_text(raw, self._map)
        if spoken:
            self._first_done = True
            out.append(spoken)
