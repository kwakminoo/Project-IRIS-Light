"""채팅 @경로 참조 — Cursor식 파일/폴더 IDE 이동."""

from __future__ import annotations

import re
from pathlib import Path

from iris.ui.chat.chat_blocks import parse_file_chip_location

# @mcp:foo 는 제외, @integrations/foo/bar.ts:12 형태 지원
_AT_PATH_RE = re.compile(
    r"(?<![\w/@])@((?:[A-Za-z]:[\\/])?[^\s@,;]+?)"
    r"(?=\s|$|[,;)}\]])"
)


def extract_at_path_refs(text: str) -> list[str]:
    """@로 시작하는 경로 참조 목록 (중복 제거, 순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _AT_PATH_RE.finditer(text or ""):
        raw = (m.group(1) or "").strip().strip('"').strip("'")
        if not raw or raw.startswith("mcp:"):
            continue
        if raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def _looks_like_path(ref: str) -> bool:
    if "/" in ref or "\\" in ref:
        return True
    if re.match(r"^[A-Za-z]:", ref):
        return True
    return "." in ref and not ref.startswith(".")


def resolve_at_path(ref: str, *, workspace_root: str = "", project_root: str = "") -> str | None:
    """@참조를 절대 파일 경로로 해석. 없으면 None."""
    path_part, _, _ = parse_file_chip_location(ref)
    path_part = (path_part or ref or "").strip()
    if not path_part or not _looks_like_path(path_part):
        return None
    candidates: list[Path] = []
    if Path(path_part).is_absolute():
        candidates.append(Path(path_part))
    else:
        for base in (workspace_root, project_root):
            if base:
                candidates.append(Path(base).expanduser() / path_part)
    for cand in candidates:
        try:
            p = cand.expanduser().resolve()
        except OSError:
            continue
        if p.is_file():
            return str(p)
    return None


def _self_check() -> None:
    refs = extract_at_path_refs("열어줘 @integrations/iris-ide/tsconfig.json 그리고 @mcp:foo")
    assert refs == ["integrations/iris-ide/tsconfig.json"]
    root = Path(__file__).resolve().parents[3]
    ws = str(root)
    resolved = resolve_at_path("integrations/iris-ide/tsconfig.json", workspace_root=ws)
    assert resolved and Path(resolved).is_file()
    p, ln, col = parse_file_chip_location("integrations/iris-ide/tsconfig.json:5:2")
    assert ln == 5 and col == 2
    print("at_path_refs ok", p)


if __name__ == "__main__":
    _self_check()
