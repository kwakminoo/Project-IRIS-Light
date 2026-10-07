"""두벌식 자판 키 순서 → 한글 문장.

저수준 키보드 훅은 IME 를 거치기 전의 키(VK)를 보므로 "안녕"을 치면 D K S S U D
가 들어온다. 입력창 글자를 직접 읽지 못했을 때 이것으로 되살린다.
"""

from __future__ import annotations

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ",
         "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

_KEY = {
    "q": "ㅂ", "w": "ㅈ", "e": "ㄷ", "r": "ㄱ", "t": "ㅅ", "y": "ㅛ", "u": "ㅕ", "i": "ㅑ",
    "o": "ㅐ", "p": "ㅔ", "a": "ㅁ", "s": "ㄴ", "d": "ㅇ", "f": "ㄹ", "g": "ㅎ", "h": "ㅗ",
    "j": "ㅓ", "k": "ㅏ", "l": "ㅣ", "z": "ㅋ", "x": "ㅌ", "c": "ㅊ", "v": "ㅍ", "b": "ㅠ",
    "n": "ㅜ", "m": "ㅡ",
    "Q": "ㅃ", "W": "ㅉ", "E": "ㄸ", "R": "ㄲ", "T": "ㅆ", "O": "ㅒ", "P": "ㅖ",
}

_VOWEL_PAIR = {
    ("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
    ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ",
}
_FINAL_PAIR = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ",
    ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ",
    ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ",
}
_FINAL_SPLIT = {v: k for k, v in _FINAL_PAIR.items()}


def _is_vowel(j: str) -> bool:
    return j in _JUNG


def _syllable(cho: str, jung: str, jong: str = "") -> str:
    if cho not in _CHO or jung not in _JUNG or jong not in _JONG:
        return cho + jung + jong
    return chr(0xAC00 + (_CHO.index(cho) * 21 + _JUNG.index(jung)) * 28 + _JONG.index(jong))


def compose(keys: str) -> str:
    """'dkssud' → '안녕'. 영문 자모 외 글자(숫자·공백·기호)는 그대로 둔다."""
    out: list[str] = []
    cho = jung = jong = ""

    def flush() -> None:
        nonlocal cho, jung, jong
        if cho and jung:
            out.append(_syllable(cho, jung, jong))
        else:
            out.append(cho + jung + jong)
        cho = jung = jong = ""

    for ch in keys:
        jamo = _KEY.get(ch) or _KEY.get(ch.lower()) if ch.isalpha() and ch.isascii() else None
        if jamo is None:
            flush()
            out.append(ch)
            continue
        if _is_vowel(jamo):
            if cho and not jung:
                jung = jamo
            elif cho and jung and not jong and (jung, jamo) in _VOWEL_PAIR:
                jung = _VOWEL_PAIR[(jung, jamo)]
            elif jong:
                # 받침이 다음 글자 초성으로 넘어간다 (안 + ㅕ → 아녀)
                if jong in _FINAL_SPLIT:
                    keep, move = _FINAL_SPLIT[jong]
                else:
                    keep, move = "", jong
                jong = keep
                flush()
                cho, jung = move, jamo
            elif not cho and jung and (jung, jamo) in _VOWEL_PAIR:
                jung = _VOWEL_PAIR[(jung, jamo)]
            else:
                flush()
                jung = jamo
        else:
            if not cho and not jung:
                cho = jamo
            elif cho and not jung:
                flush()
                cho = jamo
            elif cho and jung and not jong and jamo in _JONG:
                jong = jamo
            elif jong and (jong, jamo) in _FINAL_PAIR:
                jong = _FINAL_PAIR[(jong, jamo)]
            else:
                flush()
                cho = jamo
    flush()
    return "".join(out)
