"""Live Activity 스트림용 민감정보 제거 (thinking 한글 허용)."""

from __future__ import annotations

import re
from typing import Any

# 한국어 음절 — 스트림은 English only; 사용자/모델 문자열이 섞이면 통째로 생략
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

# Windows 드라이브 경로·홈 이스케이프
_WIN_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:\\|\\\\|/users/|/home/)[^\s\"'|<>]+"
)

# 연속 공백·제어 문자
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

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
    """싱크 진입 직전: 제어 문자·경로·시크릿·길이 처리 (한글 thinking 허용)."""
    if not raw or not raw.strip():
        return ""
    t = _CTRL_RE.sub(" ", raw)
    t = redact_secrets(t)
    t = redact_paths(t)
    if allow_multiline:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
    else:
        t = re.sub(r"\s+", " ", t.strip())
    return clamp_length(t)


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
