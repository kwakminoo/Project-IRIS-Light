"""위키 저장 의도·소스 URL/경로 파싱."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_QUOTED_PATH_RE = re.compile(
    r'["\']([^"\']+\.(?:pdf|md|markdown|txt|csv|json|html?))["\']',
    re.IGNORECASE,
)
_WIN_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\|\\\\)[^\s<>\"']+\.(?:pdf|md|markdown|txt|csv|json|html?)",
    re.IGNORECASE,
)
_POSIX_PATH_RE = re.compile(
    r"(?:~/?|/)[^\s<>\"']+\.(?:pdf|md|markdown|txt|csv|json|html?)",
    re.IGNORECASE,
)

_WIKI_WORDS = ("위키", "wiki", "옵시디언", "obsidian", "iris wiki", "iris-wiki")
_SAVE_WORDS = (
    "저장",
    "넣어",
    "넣기",
    "남겨",
    "남기",
    "기록",
    "캡처",
    "보관",
    "save",
    "import",
    "capture",
    "remember",
    "store",
)
_SUMMARIZE_WORDS = ("요약", "정리", "핵심", "summarize", "summary", "brief", "개요")


@dataclass(frozen=True)
class WikiSaveRequest:
    source: str
    mode: str  # "raw" | "summarize"
    title: str | None = None
    rel_path: str | None = None
    from_attachment: bool = False


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_wiki_save_intent(text: str, attachments: list[str] | tuple[str, ...] = ()) -> bool:
    t = _norm(text)
    has_wiki = any(w in t for w in _WIKI_WORDS)
    has_save = any(w in t for w in _SAVE_WORDS)
    if has_wiki and has_save:
        return True
    if attachments and (has_save or has_wiki):
        return True
    return False


def wants_summarize(text: str) -> bool:
    t = _norm(text)
    return any(w in t for w in _SUMMARIZE_WORDS)


def _is_url(s: str) -> bool:
    try:
        p = urlparse(s.strip())
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _valid_file(path: str) -> bool:
    p = Path(path.strip().strip('"').strip("'")).expanduser()
    return p.is_file()


def extract_source_candidates(
    text: str,
    attachments: list[str] | tuple[str, ...] = (),
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        key = s.strip()
        if not key or key in seen:
            return
        seen.add(key)
        out.append(key)

    for raw in attachments:
        p = str(raw).strip()
        if p and _valid_file(p):
            add(str(Path(p).expanduser().resolve()))

    for m in _URL_RE.finditer(text or ""):
        add(m.group(0).rstrip(".,;:)"))

    for m in _QUOTED_PATH_RE.finditer(text or ""):
        p = m.group(1)
        if _valid_file(p):
            add(str(Path(p).expanduser().resolve()))

    for pat in (_WIN_PATH_RE, _POSIX_PATH_RE):
        for m in pat.finditer(text or ""):
            p = m.group(0).rstrip(".,;:)")
            if _valid_file(p):
                add(str(Path(p).expanduser().resolve()))

    return out


def parse_wiki_save_request(
    text: str,
    attachments: list[str] | tuple[str, ...] = (),
) -> WikiSaveRequest | None:
    if not is_wiki_save_intent(text, attachments):
        return None
    candidates = extract_source_candidates(text, attachments)
    if not candidates:
        return None
    source = candidates[0]
    mode = "summarize" if wants_summarize(text) else "raw"
    from_att = bool(attachments) and source in {
        str(Path(a).expanduser().resolve()) for a in attachments if _valid_file(str(a))
    }
    return WikiSaveRequest(
        source=source,
        mode=mode,
        from_attachment=from_att,
    )
