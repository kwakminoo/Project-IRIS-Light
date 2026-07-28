"""TTS용 본문 정리/발음 치환/문장 분할."""

from __future__ import annotations

import json
import re

from iris.core.markdown_text import markdown_to_plain

DEFAULT_PRONUNCIATIONS: dict[str, str] = {
    "API": "에이피아이",
    "GPU": "지피유",
    "CPU": "씨피유",
    "PyQt": "파이큐트",
    "GitHub": "깃허브",
    "README": "리드미",
    "Ollama": "올라마",
    "Hermes": "헤르메스",
    "IRIS": "아이리스",
    "TTS": "티티에스",
    "STT": "에스티티",
}

_THINKING_LINE = re.compile(r"^\s*(thinking|tool|tools?|trace|debug|function call)\b.*$", re.IGNORECASE)
_URL = re.compile(r"https?://\S+|www\.\S+")
_PATH = re.compile(r"\b[A-Za-z]:\\[^\s]+|\b/(?:Users|home|var|tmp|opt)/[^\s]+")
_TABLE_BAR_LINE = re.compile(r"^\s*\|.*\|\s*$")
_EMOJI_RUN = re.compile(r"[\U0001F300-\U0001FAFF]+", re.UNICODE)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_CODE_FENCE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE = re.compile(r"`([^`]+)`")


def load_pronunciation_map(raw_json: str | None) -> dict[str, str]:
    mapping = dict(DEFAULT_PRONUNCIATIONS)
    if not raw_json:
        return mapping
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return mapping
    if not isinstance(data, dict):
        return mapping
    for k, v in data.items():
        key = str(k or "").strip()
        val = str(v or "").strip()
        if key and val:
            mapping[key] = val
    return mapping


def normalize_tts_text(text: str, pronunciation_map: dict[str, str] | None = None) -> str:
    t = text or ""
    t = _CODE_FENCE.sub(" ", t)
    # 줄 단위로 tool/thinking을 먼저 제거한 뒤 plain 변환 (합쳐지면 오탐)
    kept: list[str] = []
    for raw in t.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _THINKING_LINE.match(line):
            continue
        if _TABLE_BAR_LINE.match(line):
            continue
        kept.append(line)
    t = markdown_to_plain("\n".join(kept))
    lines: list[str] = []
    for raw in t.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _THINKING_LINE.match(line):
            continue
        if _TABLE_BAR_LINE.match(line):
            continue
        line = _INLINE_CODE.sub(r"\1", line)
        line = _URL.sub("", line)
        line = _PATH.sub("", line)
        line = _EMOJI_RUN.sub(" ", line)
        line = line.replace("**", " ").replace("__", " ").replace("`", " ")
        line = _MULTI_SPACE.sub(" ", line).strip()
        if line:
            lines.append(line)
    t = " ".join(lines)
    mapping = pronunciation_map or DEFAULT_PRONUNCIATIONS
    for src, dst in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        t = re.sub(rf"\b{re.escape(src)}\b", dst, t)
    t = _MULTI_SPACE.sub(" ", t).strip()
    return t


def split_tts_sentences(text: str, *, max_chars: int = 110, min_chars: int = 16) -> list[str]:
    base = normalize_tts_text(text)
    if not base:
        return []

    primary = [
        s.strip()
        for s in re.split(r"(?<=[.!?。！？])\s+|(?<=[.!?。！？])(?=[^\s])", base)
        if s.strip()
    ]
    if not primary:
        primary = [base]

    chunks: list[str] = []
    for sentence in primary:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        parts = [p.strip() for p in re.split(r"(?<=[,，;；])\s+", sentence) if p.strip()]
        if len(parts) == 1:
            parts = [sentence[i : i + max_chars].strip() for i in range(0, len(sentence), max_chars)]
        for part in parts:
            if len(part) <= max_chars:
                chunks.append(part)
            else:
                for i in range(0, len(part), max_chars):
                    chunks.append(part[i : i + max_chars].strip())

    merged: list[str] = []
    for part in chunks:
        if not merged:
            merged.append(part)
            continue
        if len(part) < min_chars:
            merged[-1] = f"{merged[-1]} {part}".strip()
        else:
            merged.append(part)
    return [c for c in merged if c]
