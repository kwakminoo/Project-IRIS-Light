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
    content: str = ""
    sources: tuple[str, ...] = ()
    followup: bool = False


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
    history: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
) -> WikiSaveRequest | None:
    if not is_wiki_save_intent(text, attachments):
        return None
    candidates = extract_source_candidates(text, attachments)
    if not candidates:
        # Only intercept an explicit reference to an existing answer. Requests to
        # research something new must still reach the agent and its search tools.
        reference = re.fullmatch(
            r"(?:방금\s*|지금\s*|아까\s*)?"
            r"(?:찾은\s*(?:정보|내용)|검색한\s*(?:정보|내용)|검색\s*결과|"
            r"이\s*(?:내용|정보|답변)|위\s*(?:내용|정보|답변)|방금\s*답변|직전\s*답변)"
            r"(?:을|를)?\s*(?:위키|wiki|옵시디언)(?:에)?\s*"
            r"(?:저장|기록|보관)(?:해\s*줘|해\s*주세요|해|해주세요)?[.!?\s]*",
            text.strip(), re.IGNORECASE,
        )
        if reference and not attachments:
            for message in reversed(history):
                if message.get("role") != "assistant":
                    continue
                content = message.get("content", "").strip()
                if not content or content.startswith(
                    ("위키에 저장했습니다", "위키 저장 실패:", "저장되었습니다")
                ):
                    return None
                title = content.splitlines()[0].lstrip("# ")[:80] or "검색 결과"
                return WikiSaveRequest(source="", mode="raw", title=title, content=content)
        return None
    source = candidates[0]
    mode = "summarize" if wants_summarize(text) else "raw"
    from_att = bool(attachments) and source in {
        str(Path(a).expanduser().resolve()) for a in attachments if _valid_file(str(a))
    }
    return WikiSaveRequest(
        source=source,
        sources=tuple(candidates),
        mode=mode,
        from_attachment=from_att,
    )


_BATCH_WORDS = ("pdf", "위키", "wiki", "저장", "파일", "첨부")
_NOTE_EXT = {".pdf", ".md", ".markdown", ".txt", ".csv", ".json", ".html", ".htm"}


def keep_wiki_batch(text: str) -> bool:
    """저장 직후 질문이면 재첨부 배치를 유지한다. 다른 화제는 끊는다."""
    body = (text or "").strip().lower()
    if not body:
        return True
    return any(word in body for word in _BATCH_WORDS)


def followup_wiki_save(
    text: str,
    attachments: list[str] | tuple[str, ...] = (),
    *,
    pending: bool,
    mode: str = "raw",
) -> WikiSaveRequest | None:
    """저장 요청 뒤에 글 없이 파일만 다시 붙이면 그 파일 전부를 같은 배치로 본다."""
    if not pending or (text or "").strip():
        return None
    candidates = extract_source_candidates("", attachments)
    if not candidates:
        return None
    return WikiSaveRequest(
        source=candidates[0],
        sources=tuple(candidates),
        mode=mode or "raw",
        from_attachment=True,
        followup=True,
    )


def reject_attachment_rewrite(paths: list[str] | tuple[str, ...] = ()) -> str:
    """첨부가 문서를 포함하면 write_user_note 대신 import_pages 를 요구한다."""
    docs = [
        str(path)
        for path in paths
        if Path(str(path)).suffix.lower() in _NOTE_EXT
    ]
    if not docs:
        return ""
    listed = "\n".join(docs)
    return (
        "첨부 파일은 wiki.import_pages 로 저장한다. "
        "wiki.write_user_note 로 본문을 다시 쓰지 말 것.\n"
        f"sources:\n{listed}"
    )
