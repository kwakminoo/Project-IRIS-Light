"""TTS 문장 펌프 + GPU를 쉬지 않고 돌리는 합성 결정."""

from __future__ import annotations

import re

from iris.audio.text_normalizer import (
    DEFAULT_PRONUNCIATIONS,
    TTS_FIRST_SENTENCE_MAX_CHARS,
    TTS_LATER_CHUNK_MAX_CHARS,
    _hard_split_overlong,
    normalize_tts_text,
)

_SENT_END = re.compile(r"[.!?。！？]")


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


def _cut_first_sentence(buf: str) -> tuple[str, str] | None:
    match = _SENT_END.search(buf)
    if match is None:
        return None
    end = match.end()
    while end < len(buf) and buf[end] in " \t\r\n":
        end += 1
    sent = buf[:end].strip()
    if not sent:
        return None
    return sent, buf[end:]


class TtsSentencePump:
    """스트림에서 완결 문장만 떼어, 첫 문장은 즉시·이후는 큰 덩어리로 내보낸다."""

    def __init__(
        self,
        pronunciation_map: dict[str, str] | None = None,
        *,
        later_max_chars: int = TTS_LATER_CHUNK_MAX_CHARS,
        first_max_chars: int = TTS_FIRST_SENTENCE_MAX_CHARS,
    ) -> None:
        self._map = pronunciation_map or DEFAULT_PRONUNCIATIONS
        self._buf = ""
        self._first_done = False
        self._pack = ""
        self._later_max = int(later_max_chars)
        self._first_max = int(first_max_chars)

    def feed(self, chunk: str) -> list[str]:
        if chunk:
            self._buf += chunk
        out: list[str] = []
        while True:
            cut = _cut_first_sentence(self._buf)
            if cut is None:
                break
            sentence, rest = cut
            self._buf = rest
            spoken = normalize_tts_text(sentence, self._map)
            if spoken:
                out.extend(self._emit(spoken))
        return out

    def flush(self) -> list[str]:
        out: list[str] = []
        out.extend(self.feed(""))
        leftover = normalize_tts_text(self._buf, self._map)
        self._buf = ""
        if leftover:
            out.extend(self._emit(leftover))
        if self._pack:
            out.append(self._pack)
            self._pack = ""
        return out

    def _emit(self, spoken: str) -> list[str]:
        if not self._first_done:
            self._first_done = True
            return _hard_split_overlong(spoken, self._first_max)
        if not self._pack:
            self._pack = spoken
        elif len(self._pack) + 1 + len(spoken) <= self._later_max:
            self._pack = f"{self._pack} {spoken}"
        else:
            done = self._pack
            self._pack = spoken
            return [done]
        if len(self._pack) >= self._later_max:
            done = self._pack
            self._pack = ""
            return [done]
        return []
