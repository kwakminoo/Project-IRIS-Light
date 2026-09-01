"""UI 표시용 민감정보·이모지 제거 (thinking 한글 허용)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# 한국어 음절 — 스트림은 English only; 사용자/모델 문자열이 섞이면 통째로 생략
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

# Windows 드라이브 경로·홈 이스케이프
_WIN_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:\\|\\\\|/users/|/home/)[^\s\"'|<>]+"
)

# 연속 공백·제어 문자
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# 이모지·장식 심볼 — 로그/채팅에는 텍스트만 (⚡ U+26A1 포함)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # pictographs … extended-A
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"  # dingbats
    "\U00002600-\U000026FF"  # misc symbols (includes ⚡)
    "\U00002300-\U000023FF"  # misc technical
    "\U00002B00-\U00002BFF"  # arrows / stars
    "\U0000200D"  # ZWJ
    "\U0000FE0E-\U0000FE0F"  # variation selectors
    "\U000020E3"  # combining enclosing keycap
    "]+",
)

# API 키·토큰 형태(짧은 휴리스틱)
_SECRET_TOKEN_RE = re.compile(
    r"\b(?:sk-[a-zA-Z0-9]{16,}|"
    r"Bearer\s+[a-zA-Z0-9._-]{20,}|"
    r"api[_-]?key\s*[:=]\s*[^\s,}]+)\b",
    re.IGNORECASE,
)

_MAX_LEN = 2000


def has_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


def _keep_text_symbol(ch: str, code: int) -> bool:
    """So여도 채팅 본문으로 쓰는 가로줄·박스 드로잉은 유지.

    U+2500 ─ 등은 한글 모음 'ㅡ'와 비슷하게 보이는데, 예전엔 So라서
    prepare_chat_text에서 통째로 사라져 채팅에 안 보였다.
    """
    # Box Drawing (─ │ ┌ …)
    if 0x2500 <= code <= 0x257F:
        return True
    # Block Elements (▀ ▄ █ …) — 구분선/다이어그램
    if 0x2580 <= code <= 0x259F:
        return True
    return False


def strip_emoji(text: str) -> str:
    """이모지·이모티콘·장식 심볼을 항상 제거. 일반 한글/영문/문장부호는 유지."""
    if not text:
        return text
    t = _EMOJI_RE.sub("", text)
    out: list[str] = []
    for ch in t:
        o = ord(ch)
        # 보충 평면 이모지·심볼
        if 0x1F000 <= o <= 0x1FFFF:
            continue
        # BMP 장식 구간 (⚡ ★ 등)
        if 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF:
            continue
        if 0x2300 <= o <= 0x23FF:
            continue
        cat = unicodedata.category(ch)
        # markdown fence / inline code delimiter (U+0060 is Sk — must not strip)
        if ch == "`":
            out.append(ch)
            continue
        # Symbol, other / modifier — 이모지·장식. 통화기호(Sc)·수학(Sm)은 유지
        if cat in ("So", "Sk", "Cs") and not _keep_text_symbol(ch, o):
            continue
        out.append(ch)
    cleaned = "".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


def redact_paths(text: str) -> str:
    return _WIN_PATH_RE.sub("[path redacted]", text)


def redact_secrets(text: str) -> str:
    t = _SECRET_TOKEN_RE.sub("[secret redacted]", text)
    return t


def clamp_length(text: str, max_len: int = _MAX_LEN) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def prepare_activity_line(raw: str, *, allow_multiline: bool = False) -> str:
    """싱크 진입 직전: 이모지·제어 문자·경로·시크릿·길이 처리 (한글 thinking 허용)."""
    if not raw or not raw.strip():
        return ""
    t = _CTRL_RE.sub(" ", raw)
    t = strip_emoji(t)
    t = redact_secrets(t)
    t = redact_paths(t)
    if allow_multiline:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
    else:
        t = re.sub(r"\s+", " ", t.strip())
    return clamp_length(t)


def prepare_chat_text(raw: str) -> str:
    """채팅창 표시용 — 이모지만 제거 (마크다운·개행 유지)."""
    if not raw:
        return ""
    t = _CTRL_RE.sub(" ", raw)
    return strip_emoji(t)


def summarize_tool_params(tool: str, params: dict[str, Any] | None) -> str:
    """도구 인자 핵심만 English 요약 (경로·전체 셸·전체 텍스트 비노출)."""
    p = params or {}
    if tool == "launch_app":
        key = str(p.get("app_key") or "").strip()
        disp = str(p.get("display_name") or "").strip()
        parts = []
        if key:
            parts.append(f"app_key={key!r}")
        if disp and not has_hangul(disp):
            parts.append(f"display_name={disp!r}")
        elif disp:
            parts.append("display_name=[redacted]")
        return ", ".join(parts) if parts else "(no app key)"
    if tool == "open_url":
        url = str(p.get("url") or "").strip()
        if not url:
            return "(no url)"
        if has_hangul(url):
            return "url=[redacted]"
        # 호스트만
        m = re.match(r"^https?://([^/]+)", url, re.I)
        host = m.group(1) if m else "[host redacted]"
        return f"host={host!r}"
    if tool == "focus_window":
        sub = str(p.get("title_sub") or "").strip()
        return f"title_sub={sub[:48]!r}" if sub else "(no title_sub)"
    if tool in ("uia_snapshot", "uia_click"):
        sub = str(p.get("window_title_sub") or "").strip()
        name = str(p.get("name") or "").strip()
        bits = []
        if sub:
            bits.append(f"window_title_sub={sub[:40]!r}")
        if name:
            bits.append("name=[withheld]" if has_hangul(name) else f"name={name[:40]!r}")
        return ", ".join(bits) if bits else "(no window target)"
    if tool == "run_shell":
        return "command=[withheld]"
    if tool == "type_text":
        return "text=[withheld]"
    if tool in ("click", "uia_click"):
        return "coords/hints=[withheld]"
    if tool == "send_hotkey":
        keys = p.get("keys") or p.get("key")
        return f"keys={str(keys)[:80]!r}"
    # 기타: 키 이름만
    keys = [k for k in p.keys() if k in ("query", "app_key", "url", "title")]
    if not keys:
        return f"param_keys={sorted(p.keys())[:6]}"
    bits = []
    for k in keys[:4]:
        v = p.get(k)
        s = str(v)[:60] if v is not None else ""
        if has_hangul(s):
            bits.append(f"{k}=[redacted]")
        else:
            bits.append(f"{k}={s!r}")
    return ", ".join(bits)


if __name__ == "__main__":
    assert "\u26a1" not in strip_emoji("Connecting via Hermes \u26a1")
    assert strip_emoji("hi \U0001F680 there") == "hi there"
    assert "\u26a1" not in prepare_activity_line("Models ready \u26a1")
    assert prepare_activity_line("plain text") == "plain text"
    assert "\u26a1" not in prepare_chat_text("답변 \u26a1 입니다")
    assert "안녕" in prepare_chat_text("안녕 \U0001F44B")
    # 한글 모음 ㅡ + 박스 가로줄(─)은 채팅에 남아야 함
    assert "\u3161" in prepare_chat_text("스나드에서 \u3161")
    assert "\u2500" in prepare_chat_text("스나드에서 \u2500\u2500\u2500")
    assert prepare_chat_text("스나드에서 \u2500\u2500") == "스나드에서 \u2500\u2500"
    print("activity_privacy self-check ok")
