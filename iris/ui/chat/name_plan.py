"""Create-turn relative path naming (vibe + Verify SSOT)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FORBIDDEN_STEMS = frozenset({"iris_generated"})

_LANG_SUFFIX = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
}

# Longer phrases first so multi-word keys win.
_PHRASE_STEMS: tuple[tuple[str, str], ...] = (
    ("이미지 명암", "image_contrast"),
    ("명암 변환", "image_contrast"),
    ("테트리스킹", "tetris_king"),
    ("테트리스", "tetris"),
    ("구구단", "gugudan"),
)

_STOP_PHRASES = (
    "만들어주세요",
    "만들어 줘",
    "만들어줘",
    "만들어 달라",
    "만들어달라",
    "작성해줘",
    "작성해 줘",
    "작성해주세요",
    "작성해 주세요",
    "코드 파일",
    "파일로 써",
    "파일 만들",
    "스크립트",
    "만들어",
    "작성",
    "코드",
    "파일",
    "해줘",
    "해주세요",
    "부탁",
    "좀",
)

_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")
_HANGUL_RUN = re.compile(r"[가-힣]+")
_CODE_DEF = re.compile(
    r"(?m)^\s*(?:def|class|function|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_STEM_CLEAN = re.compile(r"[^a-z0-9_]+")

_CHO = (
    "g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "",
    "j", "jj", "ch", "k", "t", "p", "h",
)
_JUNG = (
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe",
    "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i",
)
_JONG = (
    "", "g", "kk", "gs", "n", "nj", "nh", "d", "l", "lg", "lm", "lb", "ls",
    "lt", "lp", "lh", "m", "b", "bs", "s", "ss", "ng", "j", "ch", "k", "t",
    "p", "h",
)


@dataclass(frozen=True)
class RelPath:
    """Project-relative POSIX path. Stem never iris_generated."""

    value: str

    @classmethod
    def parse(cls, raw: str) -> RelPath | None:
        text = str(raw or "").strip().replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        if not text or text.startswith("/") or re.match(r"^[A-Za-z]:/", text):
            return None
        parts = [p for p in text.split("/") if p != ""]
        if not parts or any(p == ".." or p == "." for p in parts):
            return None
        stem = parts[-1].rsplit(".", 1)[0].casefold()
        if stem in _FORBIDDEN_STEMS:
            return None
        return cls("/".join(parts))


def lang_suffix(lang: str) -> str:
    return _LANG_SUFFIX.get((lang or "").lower(), ".py")


def _romanize_syllable(ch: str) -> str:
    code = ord(ch) - 0xAC00
    if code < 0 or code > 11171:
        return ""
    cho = code // 588
    jung = (code % 588) // 28
    jong = code % 28
    return _CHO[cho] + _JUNG[jung] + _JONG[jong]


def _romanize_hangul(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if "가" <= ch <= "힣":
            out.append(_romanize_syllable(ch))
        elif ch.isascii() and (ch.isalnum() or ch == "_"):
            out.append(ch.lower())
        elif ch in " \t-_":
            out.append("_")
    return "".join(out)


def _normalize_stem(raw: str) -> str:
    stem = _STEM_CLEAN.sub("_", (raw or "").casefold()).strip("_")
    while "__" in stem:
        stem = stem.replace("__", "_")
    if stem in _FORBIDDEN_STEMS:
        stem = "script"
    if not stem or not stem[0].isalpha():
        stem = "script" if not stem else f"s_{stem}"
    return stem[:40].rstrip("_") or "script"


def infer_english_stem(goal: str, *, code: str = "") -> str:
    """English snake_case stem from goal intent and/or code identifiers."""
    text = str(goal or "").strip()
    for phrase, stem in _PHRASE_STEMS:
        if phrase in text:
            return _normalize_stem(stem)

    latin = [m.group(0) for m in _LATIN_TOKEN.finditer(text)]
    latin = [t for t in latin if t.casefold() not in {"py", "js", "ts", "tsx", "jsx"}]
    if latin:
        return _normalize_stem("_".join(latin[:4]))

    stripped = text
    for stop in _STOP_PHRASES:
        stripped = stripped.replace(stop, " ")
    hangul_bits = _HANGUL_RUN.findall(stripped)
    if hangul_bits:
        roman = _romanize_hangul("_".join(hangul_bits))
        if roman.strip("_"):
            return _normalize_stem(roman)

    if code:
        hit = _CODE_DEF.search(code)
        if hit:
            return _normalize_stem(hit.group(1))

    return "script"


def resolve_create_rel_path(
    goal: str,
    *,
    lang: str,
    assistant: str = "",
    code: str = "",
) -> RelPath | None:
    """Single naming entry for vibe, Verify plan, and Hermes policy.

    Priority: explicit goal name → single assistant name → invent stem + lang → None.
    """
    from iris.ui.chat.file_write_claim import file_create_goal, named_rel_paths

    goal_names = named_rel_paths(goal)
    if goal_names:
        return RelPath.parse(goal_names[0])

    if assistant:
        assistant_names = named_rel_paths(assistant)
        if len(assistant_names) == 1:
            return RelPath.parse(assistant_names[0])

    if not file_create_goal(goal).matched:
        return None

    stem = infer_english_stem(goal, code=code)
    return RelPath.parse(stem + lang_suffix(lang))
